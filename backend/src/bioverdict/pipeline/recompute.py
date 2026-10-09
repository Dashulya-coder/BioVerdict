"""Recompute a finished run on added evidence (A7, the documented fallback of ADR-007).

The added evidence becomes the next bundle version, and all reasoning and scoring are run again
on that version. To keep the original run and its report untouched, the recompute is a new run
that starts from a copy of the original's evidence history; comparing the two runs gives the
diff (`api/diff.py`). Claim-level incremental recompute is not implemented.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime
from urllib.parse import urlsplit

from bioverdict.contracts import LLM
from bioverdict.llm.errors import ConfigError
from bioverdict.pipeline.reason_score import reason_and_score
from bioverdict.store.as_of import is_visible_as_of
from bioverdict.store.copy_run import copy_evidence_history
from bioverdict.store.evidence_ids import assign_ids, dedup_key
from bioverdict.store.evidence_repo import load_evidence
from bioverdict.store.freeze import freeze
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.models import Bundle, Evidence, EvidenceLevel, SourceKind, VerdictResult
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    RunRecord,
    add_event,
    create_run,
    finish_run,
    get_run,
    save_resolver,
)

log = logging.getLogger(__name__)

PARENT = "parent_run_id"  # key of a recomputed run's input that names the run it started from


class RecomputeError(ValueError):
    """The request cannot become a new bundle version; the text says why."""


def analyst_evidence(
    number: int,
    text: str,
    url: str,
    source: str,
    source_kind: SourceKind,
    level: EvidenceLevel,
    published_at: date | None,
) -> Evidence:
    """Evidence typed in by an analyst. It was not retrieved by a connector, and it says so:
    the source family and the independence group mark it as added by hand."""
    return Evidence(
        id=f"added-{number}",  # placeholder, replaced when the bundle is frozen
        source=source.strip(),
        source_family="analyst_added",
        source_kind=source_kind,
        url=url,
        excerpt=text.strip(),
        published_at=published_at,
        retrieved_at=datetime.now(UTC),
        level=level,
        independence_group=f"added:{urlsplit(url).hostname or 'unknown'}",
        version=1,
    )


def prepare_recompute(
    conn: sqlite3.Connection,
    parent_id: str,
    run_id: str,
    added: list[Evidence],
    as_of: date | None = None,
) -> Bundle:
    """Create run `run_id` from `parent_id` plus `added`, frozen as the next bundle version.

    Everything is checked before anything is written, so a refused request leaves no run behind.
    """
    parent = get_run(conn, parent_id)
    if parent is None:
        raise LookupError(f"run {parent_id} not found")
    if parent.status != DONE or parent.resolver is None:
        raise RecomputeError(f"run {parent_id} is {parent.status}: only a finished run can grow")
    cutoff = as_of or parent.as_of
    if cutoff < parent.as_of:
        raise RecomputeError(f"as_of {cutoff} is earlier than the original run's {parent.as_of}")

    hidden = [item for item in added if not is_visible_as_of(item, cutoff)]
    if hidden:
        raise RecomputeError(
            f"{len(hidden)} item(s) are dated after the cutoff {cutoff} (undated evidence counts "
            "from today); give a later as_of to include them"
        )
    existing = load_evidence(conn, parent_id)
    previous = load_bundle(conn, parent_id)
    new = assign_ids(existing, added, previous.version + 1)
    if len(new) < len(added):
        known = {dedup_key(item) for item in existing}
        repeats = sum(dedup_key(item) in known for item in added)
        raise RecomputeError(
            f"{len(added) - len(new)} item(s) add nothing: {repeats} already in the bundle, "
            "the rest repeat each other"
        )

    create_run(conn, run_id, {**parent.input, PARENT: parent_id}, cutoff)
    try:
        return _carry_over(conn, parent, run_id, added, cutoff, len(existing), len(new))
    except Exception as exc:  # the run exists now: it must not be left `running`
        log.exception("recompute %s could not be prepared", run_id)
        add_event(conn, run_id, "run", "failed", type(exc).__name__)
        finish_run(conn, run_id, FAILED)
        raise


def _carry_over(
    conn: sqlite3.Connection,
    parent: RunRecord,
    run_id: str,
    added: list[Evidence],
    cutoff: date,
    carried: int,
    new: int,
) -> Bundle:
    assert parent.resolver is not None
    parent_id = parent.run_id
    add_event(conn, run_id, "resolve", "started")
    save_resolver(conn, run_id, parent.resolver)
    add_event(conn, run_id, "resolve", "done", f"carried over from run {parent_id}")
    add_event(conn, run_id, "collect", "started", "evidence added by the analyst, no retrieval")
    copy_evidence_history(conn, parent_id, run_id)
    add_event(
        conn,
        run_id,
        "collect",
        "done",
        f"{carried} evidence items carried over, {new} added",
    )
    add_event(conn, run_id, "freeze", "started")
    bundle = freeze(conn, run_id, added, cutoff)
    add_event(
        conn, run_id, "freeze", "done", f"bundle v{bundle.version} {bundle.content_hash[:19]}"
    )
    return bundle


def finish_recompute(
    conn: sqlite3.Connection,
    run_id: str,
    bundle: Callable[[], Bundle],
    llm: Callable[[], LLM],
) -> VerdictResult | None:
    """Reason and score on the new bundle version. A failure is recorded on the run.

    The bundle and the model are obtained here, inside the guard: a missing model key or an
    unreadable bundle fails the run instead of leaving it `running` for ever.
    """
    try:
        return reason_and_score(conn, run_id, bundle(), llm())
    except Exception as exc:  # recorded on the run: the caller polls its status
        log.exception("recompute %s failed", run_id)
        shown = isinstance(exc, ConfigError)  # our own text, safe and useful to show
        add_event(
            conn,
            run_id,
            "run",
            "failed",
            f"{type(exc).__name__}: {exc}" if shown else type(exc).__name__,
        )
        finish_run(conn, run_id, FAILED)
        return None
