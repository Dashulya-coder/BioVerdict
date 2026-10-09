"""A complete run answered from fixtures: the same steps and records as a live run (A5).

The Resolver output, the frozen bundle and the model's drafts are read from `fixtures/`; reasoning
(grounding, confidence) and scoring are the real code. It lets the API and both UIs be built and
shown without the network or a model, and it is what a live run will be compared against.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from bioverdict.llm import FakeLLM
from bioverdict.pipeline.reason_score import reason_and_score
from bioverdict.store.bundle import compute_content_hash, select_bundle_evidence
from bioverdict.store.bundle_repo import save_bundle
from bioverdict.store.freeze import build_catalog
from bioverdict.store.models import Bundle, ResolverOutput, SectionStatus, VerdictResult
from bioverdict.store.runs_repo import FAILED, add_event, finish_run, get_run, save_resolver

log = logging.getLogger(__name__)


class FixtureNotFoundError(LookupError):
    """No fixture exists for the requested asset."""


def fixture_names(fixtures: Path) -> list[str]:
    """Assets for which a bundle, a resolver output and reasoning drafts all exist."""
    names = []
    for bundle in sorted((fixtures / "bundles").glob("*.json")):
        name = bundle.stem
        if (fixtures / "resolver" / f"{name}.json").exists() and (
            fixtures / "reasoning" / f"{name}.json"
        ).exists():
            names.append(name)
    return names


def _load(fixtures: Path, kind: str, name: str) -> str:
    path = fixtures / kind / f"{name}.json"
    if not path.exists():
        known = ", ".join(fixture_names(fixtures)) or "none"
        raise FixtureNotFoundError(f"no fixture {kind}/{name}.json (available: {known})")
    return path.read_text(encoding="utf-8")


def run_fixture(
    conn: sqlite3.Connection, run_id: str, asset: str, fixtures: Path
) -> VerdictResult | None:
    """Run every step for `asset` and record it. The run row must already exist.

    A failure is recorded on the run (an event and status `failed`) instead of being raised, so a
    background task cannot lose it.
    """
    name = asset.strip().casefold()
    try:
        return _run(conn, run_id, name, fixtures)
    except Exception as exc:  # recorded on the run: the caller polls its status
        log.exception("run %s failed", run_id)
        add_event(conn, run_id, "run", "failed", f"{type(exc).__name__}: {exc}")
        finish_run(conn, run_id, FAILED)
        return None


def _run(conn: sqlite3.Connection, run_id: str, name: str, fixtures: Path) -> VerdictResult:
    add_event(conn, run_id, "resolve", "started")
    resolver = ResolverOutput.model_validate_json(_load(fixtures, "resolver", name))
    save_resolver(conn, run_id, resolver)
    add_event(
        conn,
        run_id,
        "resolve",
        "done",
        f"{len(resolver.targets)} target(s), {len(resolver.assumptions)} assumption(s)",
    )

    add_event(conn, run_id, "collect", "started", "from fixtures, no network")
    bundle = Bundle.model_validate_json(_load(fixtures, "bundles", name))
    if compute_content_hash(bundle.evidence, bundle.section_statuses) != bundle.content_hash:
        raise ValueError("fixture content_hash does not match the evidence")
    run = get_run(conn, run_id)
    if run is None:
        raise ValueError(f"run {run_id} does not exist")
    visible = select_bundle_evidence(bundle.evidence, run.as_of)
    # Evidence has no section membership. Conservatively mark previously found sections
    # incomplete when the dated snapshot loses evidence; do not invent negative searches.
    statuses = {
        section: SectionStatus.INCOMPLETE
        if len(visible) < len(bundle.evidence) and status is SectionStatus.FOUND
        else status
        for section, status in bundle.section_statuses.items()
    }
    bundle = bundle.model_copy(
        update={
            "run_id": run_id,
            "bundle_id": f"B-{run_id}-v1",
            "as_of": run.as_of,
            "evidence": visible,
            "catalog": build_catalog(visible),
            "section_statuses": statuses,
            "content_hash": compute_content_hash(visible, statuses),
        }
    )
    add_event(conn, run_id, "collect", "done", f"{len(bundle.evidence)} evidence items")

    add_event(conn, run_id, "freeze", "started")
    save_bundle(conn, bundle)
    add_event(
        conn, run_id, "freeze", "done", f"bundle v{bundle.version} {bundle.content_hash[:19]}"
    )

    answers = json.loads(_load(fixtures, "reasoning", name))
    return reason_and_score(conn, run_id, bundle, FakeLLM(answers))
