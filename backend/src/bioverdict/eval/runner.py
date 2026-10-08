"""Run the regression cases and report process quality (docs/eval.md, A8).

A case is run one or more times through the same pipeline as any other run. The report compares
the verdict with the recorded expectation and adds the grounding metrics of every run. It does
not judge whether a report is right: expected risks are matched by shared words only, as a
pointer for a person to read both lists.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime
from itertools import combinations
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from bioverdict.eval.cases import EvalCase
from bioverdict.eval.metrics import RunMetrics, run_metrics
from bioverdict.store.runs_repo import create_run

# Starts and finishes one run on the connection: (conn, run_id, typed request). The run row
# exists already; a failure is recorded on the run, never raised.
StartRun = Callable[[sqlite3.Connection, str, str], object]

_WORD = re.compile(r"[a-z0-9]+")
_COMMON = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "is",
        "its",
        "of",
        "on",
        "or",
        "than",
        "that",
        "the",
        "to",
        "with",
    ]
)


class RiskMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: str
    closest: str | None  # the reported risk that shares most words with it
    shared_words: float  # Jaccard overlap of their words, 0..1; a hint, not a judgement


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    request: str
    as_of: date
    expected_verdict: list[str]
    runs: list[RunMetrics]
    verdict_as_expected: bool | None  # None: no expectation recorded, or no run finished
    # Stability is measured between runs in which a model actually answered. A repeat served
    # from the model cache, or from fixtures, replays the first answer and proves nothing.
    fresh_runs: int
    same_verdict_every_run: bool | None  # None with fewer than two fresh runs
    top_risk_overlap: float | None  # mean Jaccard of the top-risk lists between fresh runs
    risks: list[RiskMatch]


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    mode: str  # fixtures | live
    repeat: int
    cases: list[CaseResult]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold())) - _COMMON


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


def match_risks(expected: list[str], reported: list[str]) -> list[RiskMatch]:
    matches = []
    for risk in expected:
        scored = [(_jaccard(_words(risk), _words(other)), other) for other in reported]
        score, closest = max(scored, default=(0.0, None))
        matches.append(RiskMatch(expected=risk, closest=closest, shared_words=round(score, 2)))
    return matches


def run_case(
    conn: sqlite3.Connection, case: EvalCase, start: StartRun, repeat: int, today: date
) -> CaseResult:
    as_of, request = case.as_of or today, case.input.text()
    runs: list[RunMetrics] = []
    for _ in range(repeat):
        run_id = f"R-eval-{case.id}-{uuid4().hex[:8]}"
        record = {**case.input.model_dump(exclude_none=True), "eval_case": case.id}
        create_run(conn, run_id, record, as_of)
        start(conn, run_id, request)
        runs.append(run_metrics(conn, run_id))

    finished = [run for run in runs if run.verdict is not None]
    verdicts = {run.verdict for run in finished}
    expected = [verdict.value for verdict in case.expected_verdict]
    fresh = [run for run in finished if run.llm_calls > run.cache_hits]
    pairs = list(combinations(fresh, 2))
    return CaseResult(
        case_id=case.id,
        request=request,
        as_of=as_of,
        expected_verdict=expected,
        runs=runs,
        verdict_as_expected=(verdicts <= set(expected)) if expected and finished else None,
        fresh_runs=len(fresh),
        same_verdict_every_run=(
            len({run.verdict for run in fresh}) == 1 if len(fresh) > 1 else None
        ),
        top_risk_overlap=(
            round(
                statistics.fmean(_jaccard(set(a.top_risks), set(b.top_risks)) for a, b in pairs), 2
            )
            if pairs
            else None
        ),
        risks=match_risks(case.expected_top_risks, finished[0].top_risks if finished else []),
    )


def run_cases(
    conn: sqlite3.Connection,
    cases: list[EvalCase],
    start: StartRun,
    *,
    mode: str,
    repeat: int = 1,
    today: date,
) -> EvalReport:
    started = datetime.now(UTC)
    results = [run_case(conn, case, start, repeat, today) for case in cases]
    return EvalReport(started_at=started, mode=mode, repeat=repeat, cases=results)


def _share(part: int, whole: int) -> str:
    return f"{part}/{whole}" if whole else "n/a"


def _mark(value: bool | None) -> str:
    return "n/a" if value is None else "yes" if value else "NO"


def _total(runs: list[RunMetrics], field: str) -> int:
    return sum(getattr(run, field) for run in runs)


def _case_row(case: CaseResult) -> str:
    done = [run for run in case.runs if run.verdict is not None]
    failures = sorted({run.failure for run in case.runs if run.failure})
    verdict = ", ".join(sorted({str(run.verdict) for run in done})) or "failed"
    if failures:
        verdict += f" ({len(case.runs) - len(done)} failed: {'; '.join(failures)})"
    cells = [case.case_id, verdict, " or ".join(case.expected_verdict) or "none"]
    if not done:
        return "| " + " | ".join(cells + ["n/a"] * 8) + " |"
    seconds = [run.seconds for run in done if run.seconds is not None]
    cells += [
        _mark(case.verdict_as_expected),
        _mark(case.same_verdict_every_run) if case.fresh_runs > 1 or len(done) < 2 else "replayed",
        _share(_total(done, "quotes_present"), _total(done, "links")),
        _share(_total(done, "cited_in_catalog"), _total(done, "cited_evidence")),
        _share(_total(done, "sections_covered"), _total(done, "sections_required")),
        str(_total(done, "claims_dropped")),
        f"{statistics.median(seconds):.1f}" if seconds else "n/a",
        f"{statistics.median(run.cost_usd for run in done):.4f}",
    ]
    return "| " + " | ".join(cells) + " |"


def summary(report: EvalReport) -> str:
    """The table of docs/eval.md, section 7, with the totals a reader checks first."""
    runs = [run for case in report.cases for run in case.runs]
    finished = [run for run in runs if run.verdict is not None]
    verdicts = Counter(str(run.verdict) for run in finished)
    distribution = ", ".join(f"{name} {count}" for name, count in sorted(verdicts.items()))
    quotes = _share(_total(finished, "quotes_present"), _total(finished, "links"))
    honest = _share(
        _total(finished, "unknown_with_diligence_type"), _total(finished, "unknown_claims")
    )
    header = (
        "| Case | Verdict | Expected | As expected | Stable | Quotes present "
        "| Sources in catalog | Sections | Claims dropped | Time, s | Cost, USD |"
    )
    lines = [
        f"# Evaluation run, {report.started_at:%Y-%m-%d %H:%M} UTC",
        "",
        f"Mode: **{report.mode}**, {len(report.cases)} case(s), {report.repeat} run(s) each. "
        + "Counted by code from the stored records; no model judged these reports. "
        + "`Stable` compares runs a model answered afresh; `replayed` means the repeats came "
        + "from fixtures or the model cache and say nothing about stability.",
        "",
        header,
        "|" + "---|" * 11,
        *(_case_row(case) for case in report.cases),
        "",
        "## Totals",
        "",
        f"- Runs: {len(runs)}, finished {len(finished)}, failed {len(runs) - len(finished)}.",
        f"- Verdicts: {distribution or 'none'}.",
        f"- Quote presence: {quotes} links whose quote is verbatim in the evidence they name.",
        f"- Unknowns with a diligence type: {honest}.",
        f"- Citations rejected by code: {_total(finished, 'citations_rejected')}; "
        + f"claims dropped for that: {_total(finished, 'claims_dropped')}.",
        f"- Model calls: {_total(runs, 'llm_calls')} ({_total(runs, 'cache_hits')} from cache), "
        + f"cost ${sum(run.cost_usd for run in runs):.4f}.",
    ]
    risky = [case for case in report.cases if case.risks]
    if risky:
        lines += [
            "",
            "## Expected risks (matched by shared words only: read both columns)",
            "",
            "| Case | Expected | Closest reported risk | Shared words |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {case.case_id} | {risk.expected} | {risk.closest or 'none'} | {risk.shared_words} |"
            for case in risky
            for risk in case.risks
        ]
    return "\n".join(lines) + "\n"


def write_report(report: EvalReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (directory / "summary.md").write_text(summary(report), encoding="utf-8")
