"""A live run: public sources are read, frozen into a bundle, then reasoned over and scored.

The steps, the progress events and the stored records are those of a fixture run
(`fixture_run.py`), so the API, the report and the UI do not tell the two apart. The network is
used only before the freeze: the Resolver's lookups and the collection. Reasoning and scoring get
the frozen bundle and nothing else (`reason_score.py`).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable

from bioverdict.agents.collect import Collection
from bioverdict.contracts import LLM
from bioverdict.graph.collect_nodes import CollectNodes, CollectState
from bioverdict.graph.pipeline import collection_graph
from bioverdict.llm.errors import BudgetExceededError, ConfigError, RunTimeoutError
from bioverdict.pipeline.live_sources import SourcesFactory, live_sources
from bioverdict.pipeline.reason_score import reason_and_score
from bioverdict.resolver.resolver import Resolver, ResolverError
from bioverdict.store.models import Bundle, SectionStatus, VerdictResult
from bioverdict.store.runs_repo import FAILED, add_event, finish_run, get_run, save_resolver

log = logging.getLogger(__name__)

LLMFactory = Callable[[str], LLM]  # run id in, the model of that run out
# One live run to its end on the given connection: (conn, run_id, typed request). The API and
# the CLI take one, so tests can replace the sources and the model.
LiveRunner = Callable[[sqlite3.Connection, str, str], VerdictResult | None]


class NoEvidenceError(RuntimeError):
    """Nothing was collected because sources failed: there is no bundle to reason over."""


# Errors written by this code base: their text is safe to show. Anything else may quote a
# provider's answer or a credential, so only its class is recorded and the rest is logged.
_SHOWN = (ResolverError, NoEvidenceError, ConfigError, BudgetExceededError, RunTimeoutError)


def describe_request(asset: str | None, indication: str | None, mechanism: str | None) -> str:
    """One line for the Resolver from the fields of a run request; empty when all are blank."""
    asset, indication, mechanism = (
        (value or "").strip() for value in (asset, indication, mechanism)
    )
    subject = " for ".join(part for part in (mechanism, indication) if part)
    return ": ".join(part for part in (asset, subject) if part)


def run_live(
    conn: sqlite3.Connection,
    run_id: str,
    text: str,
    llm_factory: LLMFactory,
    sources: SourcesFactory = live_sources,
) -> VerdictResult | None:
    """Run every step for the typed request and record it. The run row must already exist.

    A failure is recorded on the run (an event and status `failed`) instead of being raised, so a
    background task cannot lose it. Blocks until the run ends; call it off the event loop.
    """
    try:
        llm = llm_factory(run_id)
        bundle = asyncio.run(_resolve_and_collect(conn, run_id, text, llm, sources))
        return reason_and_score(conn, run_id, bundle, llm)
    except Exception as exc:  # recorded on the run: the caller polls its status
        log.exception("run %s failed", run_id)
        reason = f"{type(exc).__name__}: {exc}" if isinstance(exc, _SHOWN) else type(exc).__name__
        add_event(conn, run_id, "run", "failed", reason)
        finish_run(conn, run_id, FAILED)
        return None


async def _resolve_and_collect(
    conn: sqlite3.Connection, run_id: str, text: str, llm: LLM, sources: SourcesFactory
) -> Bundle:
    run = get_run(conn, run_id)
    if run is None:
        raise ValueError(f"run {run_id} does not exist")

    async with sources(conn) as source:
        add_event(conn, run_id, "resolve", "started")
        resolved = await Resolver(source.lookup, llm).resolve(text)
        save_resolver(conn, run_id, resolved)
        add_event(
            conn,
            run_id,
            "resolve",
            "done",
            f"{len(resolved.targets)} target(s), {len(resolved.assumptions)} assumption(s)",
        )

        add_event(conn, run_id, "collect", "started", ", ".join(sorted(source.tools)))
        graph = collection_graph(CollectNodes(conn, source.plans, source.tools, llm))
        state: CollectState = {"run_id": run_id, "query": resolved, "as_of": run.as_of}
        bundle: Bundle | None = None
        # The graph runs on this thread, which owns the SQLite connection.
        async for update in graph.astream(state, stream_mode="updates"):
            if "collect" in update:
                collection: Collection = update["collect"]["collection"]
                _require_evidence(collection)
                add_event(conn, run_id, "collect", "done", _summary(collection))
                add_event(conn, run_id, "freeze", "started")
            if "freeze" in update:
                bundle = update["freeze"]["bundle"]

    if bundle is None:
        raise RuntimeError("the collection graph ended without a bundle")
    add_event(
        conn, run_id, "freeze", "done", f"bundle v{bundle.version} {bundle.content_hash[:19]}"
    )
    return bundle


def _require_evidence(collection: Collection) -> None:
    """An empty bundle is an answer only if the sources were read to the end.

    A section that failed or was cut short (a source error, a timeout) and left nothing behind
    says nothing about the asset; reasoning over it would report gaps that are not findings.
    """
    unread = (SectionStatus.ERROR, SectionStatus.INCOMPLETE)
    failed = [s for s in collection.sections if s.status in unread]
    if failed and not collection.evidence:
        detail = "; ".join(
            f"{s.section.value} {s.status.value} ({', '.join(s.issues) or 'cut short'})"
            for s in failed
        )
        raise NoEvidenceError(f"no evidence was collected and these sections failed: {detail}")


def _summary(collection: Collection) -> str:
    """Every planned section with its status, what was rejected and what could not be read."""
    parts = []
    for section in collection.sections:
        text = f"{section.section.value}={section.status.value} ({len(section.facts)} facts"
        if section.rejected:
            text += f", {len(section.rejected)} rejected"
        text += ")"
        if section.issues:
            text += f" [{', '.join(section.issues)}]"
        parts.append(text)
    return f"{len(collection.evidence)} evidence items; " + "; ".join(parts)
