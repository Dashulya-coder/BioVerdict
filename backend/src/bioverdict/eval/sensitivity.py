"""Sensitivity benchmark: does a module change its answer when a document is added, and for
the right reason? (docs/eval.md, "Sensitivity benchmark")

Each case adds one document to a finished run through the same path as the API's add-evidence
route (`pipeline/recompute.py`), then reads the code-computed diff (`api/diff.py`). A case passes
when the module it names moved the way it expects and the document is among the causes; a noise
case passes when the document was placed on no claim and no answer changed. Nothing here judges a
report with a model.

A recompute at a later cutoff ages every claim, so a case compared with the base run would show
that drift as if the document had caused it. Each case is therefore compared with a control: the
base run recomputed at the same cutoff with no document (one control per cutoff, shared by its
cases). The control and the case differ only in the document, so what the diff shows is its effect.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date as date_type
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from bioverdict.api.diff import build_diff
from bioverdict.api.schemas import AddedEvidence, DiffResponse, ModuleChange
from bioverdict.contracts import LLM
from bioverdict.pipeline.recompute import (
    RecomputeError,
    analyst_evidence,
    finish_recompute,
    prepare_recompute,
)
from bioverdict.scoring.module_answers import ModuleId
from bioverdict.store.runs_repo import get_run, load_events

Kind = Literal["strong", "weak", "noise"]
Direction = Literal["down", "up", "none"]
# A weak document may move a balance; it must not move it this far or change the answer.
WEAK_MAX_SHIFT = 0.15


class Expectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: ModuleId | None = None  # none for a noise case: no module may move
    direction: Direction


class SensitivityCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    kind: Kind
    item: str = Field(description="What the document is: the dataset item, by its public id")
    document: AddedEvidence
    expect: Expectation
    as_of: date_type | None = None  # default: the base run's cutoff


class CaseOutcome(BaseModel):
    case_id: str
    kind: Kind
    item: str
    run_id: str | None
    passed: bool
    reason: str
    control_run: str | None = None  # the run every "before" below is read from
    module: ModuleId | None = None
    answer_before: str | None = None
    answer_after: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None
    moved_modules: list[str] = []
    verdict_before: str | None = None
    verdict_after: str | None = None


class SensitivityReport(BaseModel):
    base_run: str
    controls: dict[str, str] = {}  # cutoff -> the base run recomputed at it with no document
    cases: list[CaseOutcome]

    @property
    def passed(self) -> int:
        return sum(case.passed for case in self.cases)


_CASES = TypeAdapter(list[SensitivityCase])


def load_cases(path: Path) -> list[SensitivityCase]:
    cases = _CASES.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be unique")
    return cases


def _shift(change: ModuleChange) -> float:
    return (change.balance_after or 0.0) - (change.balance_before or 0.0)


def judge_case(case: SensitivityCase, diff: DiffResponse) -> tuple[bool, str]:
    """Whether the diff shows what the case expects, and the sentence that says why."""
    added = {item.id for item in diff.evidence_added}
    if case.expect.direction == "none":
        # The diff is against the control at the same cutoff, so nothing here is drift with a
        # later cutoff: noise must not be placed on a claim, change an answer or the verdict.
        touched = [m for m in diff.modules if any(c.evidence_id in added for c in m.causes)]
        flipped = [m for m in diff.modules if m.answer_before is not m.answer_after]
        if touched or flipped or diff.verdict_changed:
            names = sorted({m.module.value for m in [*touched, *flipped]})
            return False, "moved: " + (", ".join(names) or "the verdict")
        return True, "no module moved"

    target = next((m for m in diff.modules if m.module is case.expect.module), None)
    if target is None:
        return False, f"the diff has no module {case.expect.module}"
    if not any(cause.evidence_id in added for cause in target.causes):
        return False, "the document is not among the causes of this module"
    shift = _shift(target)
    wanted = shift < 0 if case.expect.direction == "down" else shift > 0
    if not wanted:
        return False, f"balance moved {shift:+.2f}, expected {case.expect.direction}"
    if case.kind == "weak":
        if target.answer_before is not target.answer_after:
            return False, "a weak document changed the module's answer"
        if abs(shift) > WEAK_MAX_SHIFT:
            return False, f"a weak document moved the balance {shift:+.2f}"
        if diff.verdict_changed:
            return False, "a weak document changed the verdict"
    return True, f"balance moved {shift:+.2f} and the document is named as the cause"


def _blank(case: SensitivityCase, **changes: object) -> CaseOutcome:
    return CaseOutcome(
        case_id=case.id,
        kind=case.kind,
        item=case.item,
        run_id=None,
        passed=False,
        reason="",
        **changes,
    )


def run_control(
    conn: sqlite3.Connection,
    base_run: str,
    cutoff: date_type | None,
    llm: Callable[[str], LLM],
) -> tuple[str | None, str]:
    """The base run recomputed at `cutoff` with no document: the run to compare a case with.

    Returns its run id, or None and why it could not be made. With nothing to place, the model
    is not asked to classify anything; code only ages and rescores the claims at the cutoff.
    """
    run_id = f"R-{uuid4().hex}"
    try:
        bundle = prepare_recompute(conn, base_run, run_id, [], cutoff)
    except (LookupError, RecomputeError) as exc:
        return None, f"not run: {exc}"
    if finish_recompute(conn, run_id, lambda: bundle, lambda: llm(run_id)) is None:
        return None, f"control run failed: {load_events(conn, run_id)[-1].detail}"
    return run_id, ""


def run_case(
    conn: sqlite3.Connection,
    base_run: str,
    case: SensitivityCase,
    llm: Callable[[str], LLM],
    control_run: str,
) -> CaseOutcome:
    """Add the case's document to `base_run` and compare the result with `control_run`."""
    doc = case.document
    evidence = analyst_evidence(
        1, doc.text, doc.url, doc.source, doc.source_kind, doc.level, doc.published_at
    )
    run_id = f"R-{uuid4().hex}"
    blank = _blank(case, control_run=control_run)
    try:
        bundle = prepare_recompute(conn, base_run, run_id, [evidence], case.as_of)
    except (LookupError, RecomputeError) as exc:
        return blank.model_copy(update={"reason": f"not run: {exc}"})
    result = finish_recompute(conn, run_id, lambda: bundle, lambda: llm(run_id))
    if result is None:
        why = load_events(conn, run_id)[-1].detail
        return blank.model_copy(update={"run_id": run_id, "reason": f"run failed: {why}"})

    diff = build_diff(conn, control_run, run_id)
    passed, reason = judge_case(case, diff)
    target = next((m for m in diff.modules if m.module is case.expect.module), None)
    return CaseOutcome(
        case_id=case.id,
        kind=case.kind,
        item=case.item,
        run_id=run_id,
        control_run=control_run,
        passed=passed,
        reason=reason,
        module=case.expect.module,
        answer_before=target.answer_before.value if target else None,
        answer_after=target.answer_after.value if target else None,
        balance_before=target.balance_before if target else None,
        balance_after=target.balance_after if target else None,
        moved_modules=[m.module.value for m in diff.modules if m.changed],
        verdict_before=diff.base.verdict.value,
        verdict_after=diff.head.verdict.value,
    )


def run_cases(
    conn: sqlite3.Connection,
    base_run: str,
    cases: list[SensitivityCase],
    llm: Callable[[str], LLM],
) -> SensitivityReport:
    """Run every case against the control of its cutoff (one control per cutoff, made once)."""
    base = get_run(conn, base_run)
    controls: dict[date_type | None, tuple[str | None, str]] = {}
    outcomes = []
    for case in cases:
        cutoff = case.as_of or (base.as_of if base else None)
        if cutoff not in controls:
            controls[cutoff] = run_control(conn, base_run, cutoff, llm)
        control, why = controls[cutoff]
        if control is None:
            outcomes.append(_blank(case).model_copy(update={"reason": why}))
        else:
            outcomes.append(run_case(conn, base_run, case, llm, control))
    return SensitivityReport(
        base_run=base_run,
        controls={
            cutoff.isoformat(): run for cutoff, (run, _) in controls.items() if run and cutoff
        },
        cases=outcomes,
    )


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def summary(report: SensitivityReport) -> str:
    lines = [
        f"# Sensitivity benchmark on run {report.base_run}",
        "",
        f"{report.passed} of {len(report.cases)} case(s) passed.",
        "",
        (
            "Each case is compared with a control: the base run recomputed at the same cutoff "
            "with no document, so a later cutoff does not show as an effect of the document. "
            "Before = the control."
        ),
        *(f"- Control at {cutoff}: run {run}" for cutoff, run in report.controls.items()),
        "",
        "| Case | Kind | Dataset item | Module | Answer | Balance | Verdict | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in report.cases:
        answer = f"{case.answer_before} → {case.answer_after}" if case.answer_after else "-"
        balance = f"{_number(case.balance_before)} → {_number(case.balance_after)}"
        verdict = f"{case.verdict_before} → {case.verdict_after}" if case.verdict_after else "-"
        mark = "pass" if case.passed else "FAIL"
        lines.append(
            f"| {case.case_id} | {case.kind} | {case.item} | "
            f"{case.module.value if case.module else 'any'} | {answer} | "
            f"{balance if case.module else '-'} | {verdict} | {mark}: {case.reason} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: SensitivityReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sensitivity.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (directory / "sensitivity.md").write_text(summary(report), encoding="utf-8")
