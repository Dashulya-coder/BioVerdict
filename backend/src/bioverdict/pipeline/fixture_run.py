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
from bioverdict.reasoning import ModuleReasoner
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.bundle_repo import save_bundle
from bioverdict.store.models import Bundle, ResolverOutput, VerdictResult
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    add_event,
    finish_run,
    save_claims,
    save_resolver,
)

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
    bundle = bundle.model_copy(update={"run_id": run_id, "bundle_id": f"B-{run_id}-v1"})
    add_event(conn, run_id, "collect", "done", f"{len(bundle.evidence)} evidence items")

    add_event(conn, run_id, "freeze", "started")
    save_bundle(conn, bundle)
    add_event(
        conn, run_id, "freeze", "done", f"bundle v{bundle.version} {bundle.content_hash[:19]}"
    )

    add_event(conn, run_id, "reason", "started", "mechanism, translation")
    answers = json.loads(_load(fixtures, "reasoning", name))
    reasoner = ModuleReasoner(FakeLLM(answers), run_id)
    claims, links = reasoner.reason(bundle)
    save_claims(conn, run_id, claims, links, bundle.version)
    dropped = len(reasoner.trace.drops)
    add_event(conn, run_id, "reason", "done", f"{len(claims)} claims, {dropped} dropped by code")

    add_event(conn, run_id, "score", "started")
    result = score_verdict(claims)
    add_event(conn, run_id, "score", "done", f"{result.verdict.value} ({result.confidence:.2f})")

    finish_run(conn, run_id, DONE, result)
    add_event(conn, run_id, "run", "done")
    return result
