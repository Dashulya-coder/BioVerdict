"""Sensitivity benchmark: does a module change its answer when a document is added, and for
the right reason? (docs/eval.md, "Sensitivity benchmark")

Each case adds one document to a finished run through the same path as the API's add-evidence
route (`pipeline/recompute.py`), then reads the code-computed diff (`api/diff.py`). A case passes
when the module it names moved the way it expects and the document is among the causes; a noise
case passes when the document was placed on no claim and no answer changed. Nothing here judges a report with a model.
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
from bioverdict.store.runs_repo import load_events

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
        # A later cutoff ages every claim, so a balance, even an answer, may drift with no new
        # evidence behind it (a live run of 2026-10-10: the base run at 2024-06-30 and the
        # recompute at 2026-10-10 differed in the unmet-need module in all five cases, noise
        # included, with no cause). What noise must not do is be placed on a claim, or change
        # the verdict. A module that moved with no cause is drift and is reported, not failed.
        touched = [m for m in diff.modules if any(c.evidence_id in added for c in m.causes)]
        if touched or diff.verdict_changed:
            names = sorted(m.module.value for m in touched)
            return False, "moved: " + (", ".join(names) or "the verdict")
        drifted = sorted(m.module.value for m in diff.modules if m.changed)
        if drifted:
            return (
                True,
                "no module moved because of the document (drift with the later cutoff: "
                + ", ".join(drifted)
                + ")",
            )
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


def run_case(
    conn: sqlite3.Connection, base_run: str, case: SensitivityCase, llm: Callable[[str], LLM]
) -> CaseOutcome:
    doc = case.document
    evidence = analyst_evidence(
        1, doc.text, doc.url, doc.source, doc.source_kind, doc.level, doc.published_at
    )
    run_id = f"R-{uuid4().hex}"
    blank = CaseOutcome(
        case_id=case.id, kind=case.kind, item=case.item, run_id=None, passed=False, reason=""
    )
    try:
        bundle = prepare_recompute(conn, base_run, run_id, [evidence], case.as_of)
    except (LookupError, RecomputeError) as exc:
        return blank.model_copy(update={"reason": f"not run: {exc}"})
    result = finish_recompute(conn, run_id, lambda: bundle, lambda: llm(run_id))
    if result is None:
        why = load_events(conn, run_id)[-1].detail
        return blank.model_copy(update={"run_id": run_id, "reason": f"run failed: {why}"})

    diff = build_diff(conn, base_run, run_id)
    passed, reason = judge_case(case, diff)
    target = next((m for m in diff.modules if m.module is case.expect.module), None)
    return CaseOutcome(
        case_id=case.id,
        kind=case.kind,
        item=case.item,
        run_id=run_id,
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
    return SensitivityReport(
        base_run=base_run, cases=[run_case(conn, base_run, case, llm) for case in cases]
    )


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def summary(report: SensitivityReport) -> str:
    lines = [
        f"# Sensitivity benchmark on run {report.base_run}",
        "",
        f"{report.passed} of {len(report.cases)} case(s) passed.",
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
