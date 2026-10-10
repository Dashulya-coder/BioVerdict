"""Sensitivity probes (docs/eval.md, section 3): does the verdict move as much as the evidence says?

A finished run is grown by one added document (the recompute of A7) and compared with the run it
grew from (the diff of A7). Whether the change is right for the kind of document is decided here,
by code, from the stored records of the two runs; no model judges it:

- strong: the verdict moves in the stated direction, or a key claim's confidence moves that way
  by at least `STRONG_MOVE`, or a gate newly fires (lower) or stops firing (higher);
- weak: the verdict does not change, no gate changes, and some confidence moves in the stated
  direction by at least `NOISE_BAND`;
- noise: nothing moves: the verdict, the gates and the status of every chain link stay, no claim
  appears or goes, and every confidence stays within `NOISE_BAND` (the drift of a few thousandths
  that the passing of time puts on evidence with a half-life is inside it).

A probe whose run could not be made (the model failed, the document repeats the bundle, it is
dated after the cutoff) is `passed=None` with the reason, never a pass.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel, ConfigDict

from bioverdict.api.diff import build_diff
from bioverdict.api.schemas import DiffResponse
from bioverdict.eval.cases import Probe
from bioverdict.pipeline.recompute import RecomputeError, analyst_evidence, prepare_recompute
from bioverdict.store.models import Evidence, Verdict
from bioverdict.store.runs_repo import DONE, get_run

STRONG_MOVE = 0.10  # a key claim must move this much when the verdict itself cannot (a placeholder)
NOISE_BAND = 0.02  # a confidence inside this band has not moved (a placeholder)
_RANK = {Verdict.INVEST: 0, Verdict.CONDITIONAL: 1, Verdict.DO_NOT_INVEST: 2}

# Carries out the recompute that `prepare_recompute` set up: (conn, new run id). The run exists
# and is `running`; a failure is recorded on it, never raised.
FinishRecompute = Callable[[sqlite3.Connection, str], object]


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    direction: str | None
    note: str
    run_id: str | None
    passed: bool | None  # None: the probe could not be run or says nothing; see `reason`
    reason: str
    verdict_before: str | None = None
    verdict_after: str | None = None
    confidence_before: float | None = None
    confidence_after: float | None = None
    claims_moved: int = 0  # claims whose confidence moved by more than the noise band
    claims_added: int = 0
    claims_removed: int = 0


def _signed(delta: float, direction: str) -> float:
    """`delta` counted positive when it moves the way the probe says."""
    return -delta if direction == "lower" else delta


def judge(probe: Probe, diff: DiffResponse) -> tuple[bool, str]:
    """Whether the run moved as this kind of document should move it, and why."""
    base, head = diff.base, diff.head
    steps = _RANK[head.verdict] - _RANK[base.verdict]  # positive: worse
    verdict_dir = 0 if steps == 0 else (1 if steps > 0 else -1)
    wanted = 0 if probe.direction is None else (1 if probe.direction == "lower" else -1)
    deltas = [
        c.after.confidence - c.before.confidence
        for c in diff.claims
        if c.change == "changed" and c.before is not None and c.after is not None
    ]
    key_deltas = [
        c.after.confidence - c.before.confidence
        for c in diff.claims
        if c.change == "changed"
        and c.before is not None
        and c.after is not None
        and (c.before.critical or c.after.critical)
    ]
    added = [c for c in diff.claims if c.change == "added"]
    removed = [c for c in diff.claims if c.change == "removed"]
    conf_delta = head.confidence - base.confidence

    if probe.kind == "noise":
        moved = [d for d in deltas if abs(d) > NOISE_BAND]
        chain_moved = [c for c in diff.chain if c.status_before != c.status_after]
        if diff.verdict_changed or diff.gates or chain_moved or added or removed or moved:
            return False, (
                f"an irrelevant document changed the run: verdict {base.verdict.value} -> "
                f"{head.verdict.value}, {len(moved)} confidence(s) moved, {len(added)} claim(s) "
                f"added, {len(removed)} removed, {len(diff.gates)} gate(s) changed"
            )
        return True, "nothing moved"

    assert probe.direction is not None
    if probe.kind == "strong":
        if verdict_dir == wanted and wanted != 0:
            return (
                True,
                f"the verdict moved {probe.direction}: {base.verdict.value} -> {head.verdict.value}",
            )
        gate_moved = any(
            g.fired_after and not g.fired_before
            if probe.direction == "lower"
            else g.fired_before and not g.fired_after
            for g in diff.gates
        )
        if gate_moved:
            return True, "a gate changed state in the stated direction"
        key = max((_signed(d, probe.direction) for d in key_deltas), default=0.0)
        if key >= STRONG_MOVE:
            return True, f"a key claim's confidence moved {probe.direction} by {key:.2f}"
        return False, (
            f"a decisive document left the verdict at {head.verdict.value} and moved no key claim "
            f"{probe.direction} by {STRONG_MOVE} (largest move {max(key, 0.0):.2f})"
        )

    # weak
    if diff.verdict_changed:
        return (
            False,
            f"a minor document flipped the verdict: {base.verdict.value} -> {head.verdict.value}",
        )
    if diff.gates:
        return False, "a minor document changed a gate"
    moves = [_signed(d, probe.direction) for d in [*deltas, conf_delta]]
    if max(moves, default=0.0) >= NOISE_BAND:
        return True, f"confidence moved {probe.direction} and the verdict held"
    return False, f"a minor document moved no confidence {probe.direction}"


def run_probe(
    conn: sqlite3.Connection,
    base_run_id: str,
    probe: Probe,
    finish: FinishRecompute,
    new_run_id: str,
) -> ProbeResult:
    """Grow the finished run `base_run_id` by the probe's document and judge what moved."""
    result = ProbeResult(
        kind=probe.kind,
        direction=probe.direction,
        note=probe.note,
        run_id=None,
        passed=None,
        reason="",
    )
    base = get_run(conn, base_run_id)
    if base is None or base.status != DONE:
        result.reason = "the case's run did not finish, so there is nothing to grow"
        return result
    document = probe.evidence
    added: list[Evidence] = [
        analyst_evidence(
            1,
            document.text,
            document.url,
            document.source,
            document.source_kind,
            document.level,
            document.published_at,
        )
    ]
    cutoff: date | None = probe.as_of
    try:
        prepare_recompute(conn, base_run_id, new_run_id, added, cutoff)
    except RecomputeError as exc:
        result.reason = f"the document could not be added: {exc}"
        return result
    result.run_id = new_run_id
    finish(conn, new_run_id)
    head = get_run(conn, new_run_id)
    if head is None or head.status != DONE:
        result.reason = "the recompute failed"
        return result
    diff = build_diff(conn, base_run_id, new_run_id)
    result.passed, result.reason = judge(probe, diff)
    result.verdict_before, result.verdict_after = diff.base.verdict.value, diff.head.verdict.value
    result.confidence_before, result.confidence_after = diff.base.confidence, diff.head.confidence
    changed = [c for c in diff.claims if c.change == "changed" and c.before and c.after]
    result.claims_moved = sum(
        abs(c.after.confidence - c.before.confidence) > NOISE_BAND  # type: ignore[union-attr]
        for c in changed
    )
    result.claims_added = sum(c.change == "added" for c in diff.claims)
    result.claims_removed = sum(c.change == "removed" for c in diff.claims)
    return result
