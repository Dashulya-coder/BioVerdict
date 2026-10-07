"""Exercise A4 collection -> extraction -> freeze offline, without the pending run API."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import date
from pathlib import Path

from bioverdict.agents.collect import CollectPlan
from bioverdict.connectors.fake import FakeConnector
from bioverdict.graph.collect_nodes import CollectNodes
from bioverdict.graph.pipeline import collection_graph
from bioverdict.llm import FakeLLM
from bioverdict.store.as_of import is_visible_as_of
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle, Indication, ResolverOutput, Section, Target

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=Path("/tmp/bioverdict-collection.db")
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 10, 7))
    args = parser.parse_args()
    fixture = Bundle.model_validate_json(
        (ROOT / "fixtures/bundles/divarasib.json").read_text(encoding="utf-8")
    )
    # A canned extraction over real fixture text, not a fresh medical conclusion.
    record = fixture.evidence_by_id()["E-0007"]
    facts = (
        []
        if not is_visible_as_of(record, args.as_of)
        else [{"source_id": record.id, "quote": record.excerpt, "value": "53.4%"}]
    )
    query = ResolverOutput(
        indication=Indication(name="non-small cell lung carcinoma"),
        targets=[Target(symbol="KRAS")],
        known_assets=["divarasib"],
    )
    with closing(connect(args.db)) as conn:
        migrate(conn)
        graph = collection_graph(
            CollectNodes(
                conn,
                [CollectPlan(section=Section.CLINICAL, tools=("fixture",))],
                {"fixture": FakeConnector([record])},
                FakeLLM({"extraction": {"facts": facts}}),
            )
        )
        output = await graph.ainvoke(
            {
                "run_id": f"R-collect-fixture-{args.as_of}",
                "query": query,
                "as_of": args.as_of,
            }
        )
        print(output["bundle"].model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
