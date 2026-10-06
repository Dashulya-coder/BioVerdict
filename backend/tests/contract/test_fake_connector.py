from datetime import UTC, date, datetime
from pathlib import Path

from bioverdict.connectors.fake import FakeConnector
from bioverdict.contracts import Connector
from bioverdict.store.models import (
    Bundle,
    Evidence,
    EvidenceLevel,
    Indication,
    ResolverOutput,
    SourceKind,
    Target,
)

QUERY = ResolverOutput(indication=Indication(name="NSCLC"), targets=[Target(symbol="KRAS")])


def _evidence(eid: str, published_at: date | None) -> Evidence:
    return Evidence(
        id=eid,
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url="https://clinicaltrials.gov/study/NCT00000000",
        excerpt="text",
        published_at=published_at,
        retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
        level=EvidenceLevel.HUMAN_INTERVENTIONAL,
        independence_group="sponsor:test",
        version=1,
    )


def test_satisfies_connector_protocol() -> None:
    assert isinstance(FakeConnector([]), Connector)


async def test_as_of_excludes_later_evidence() -> None:
    old, new = _evidence("E-1", date(2024, 1, 1)), _evidence("E-2", date(2026, 7, 2))
    result = await FakeConnector([old, new]).fetch(QUERY, date(2025, 1, 1))
    assert [e.id for e in result] == ["E-1"]


async def test_as_of_boundary_is_inclusive() -> None:
    e = _evidence("E-1", date(2025, 1, 1))
    assert await FakeConnector([e]).fetch(QUERY, date(2025, 1, 1)) == [e]


async def test_undated_snapshot_follows_retrieval_date() -> None:
    e = _evidence("E-1", None)  # retrieved 2026-10-06
    connector = FakeConnector([e])
    assert await connector.fetch(QUERY, date(2026, 10, 6)) == [e]
    assert await connector.fetch(QUERY, date(2026, 10, 5)) == []


async def test_from_bundle_file(tmp_path: Path) -> None:
    bundle = Bundle(
        bundle_id="B-1",
        run_id="R-1",
        version=1,
        as_of=date(2026, 10, 6),
        content_hash="sha256:x",
        catalog=[],
        evidence=[_evidence("E-1", date(2024, 1, 1))],
        created_at=datetime(2026, 10, 6, tzinfo=UTC),
    )
    path = tmp_path / "bundle.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    result = await FakeConnector.from_bundle_file(path).fetch(QUERY, date(2026, 10, 6))
    assert [e.id for e in result] == ["E-1"]
