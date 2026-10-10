"""The eval runner and its metrics, on fixture runs: no network, no model."""

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.eval.cases import EvalCase, load_cases
from bioverdict.eval.metrics import REQUIRED_SECTIONS, run_metrics
from bioverdict.eval.runner import match_risks, run_cases, summary, write_report
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Section
from bioverdict.store.runs_repo import create_run
from bioverdict.store.verification_repo import load_checks

FIXTURES = Path(__file__).parents[3] / "fixtures"
CASES = Path(__file__).parents[3] / "eval" / "cases.yaml"
TODAY = date(2026, 10, 7)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "eval.db")
    migrate(connection)
    yield connection
    connection.close()


def start(conn: sqlite3.Connection, run_id: str, text: str):
    return run_fixture(conn, run_id, text.casefold(), FIXTURES)


def fixture_run(conn: sqlite3.Connection, as_of: date, run_id: str = "R-1") -> None:
    create_run(conn, run_id, {"asset": "divarasib"}, as_of)
    start(conn, run_id, "divarasib")


def case(**fields) -> EvalCase:
    return EvalCase.model_validate({"id": "c1", "input": {"asset": "divarasib"}, **fields})


# --- metrics ----------------------------------------------------------------------------------


def test_a_grounded_run_has_every_quote_in_its_evidence_and_every_source_in_the_catalog(
    conn,
) -> None:
    fixture_run(conn, TODAY)

    m = run_metrics(conn, "R-1")

    assert (m.status, m.verdict, m.failure) == ("done", "Conditional", None)
    assert m.links > 0 and m.quotes_present == m.links
    assert m.cited_evidence > 0 and m.cited_in_catalog == m.cited_evidence
    assert (m.evidence, m.citations_rejected, m.claims_dropped) == (15, 0, 0)
    assert m.confidence is not None and m.top_risks and m.seconds is not None


def test_every_required_section_is_spoken_to_and_unknowns_say_what_would_answer_them(conn) -> None:
    fixture_run(conn, TODAY)

    m = run_metrics(conn, "R-1")

    assert Section.TRANSLATION in REQUIRED_SECTIONS
    assert m.sections_covered == m.sections_required == len(REQUIRED_SECTIONS)
    assert m.unknown_claims > 0 and m.unknown_with_diligence_type == m.unknown_claims


def test_citations_of_evidence_after_the_cutoff_are_counted_and_logged(conn) -> None:
    """The drafts cite documents published after 2026-06-30: the post-cutoff leak the quote
    gate must stop. What it stopped is in the verification log, not only in a counter."""
    fixture_run(conn, date(2026, 6, 30))

    m, checks = run_metrics(conn, "R-1"), load_checks(conn, "R-1")

    assert m.citations_rejected > 0 and m.claims_dropped > 0
    assert m.quotes_present == m.links  # what survived is still fully grounded
    rejected = [c for c in checks if c.check_name == "quote_in_source"]
    dropped = [c for c in checks if c.check_name == "claim_dropped"]
    assert len(rejected) == m.citations_rejected and len(dropped) == m.claims_dropped
    assert all(
        not c.passed and c.detail
        for c in checks
        if c.check_name in {"quote_in_source", "claim_dropped"}
    )
    assert {c.claim_id for c in rejected} <= {c.claim_id for c in dropped}


def test_a_failed_run_reports_its_reason_and_no_quality_numbers(conn) -> None:
    create_run(conn, "R-1", {"asset": "nothing"}, TODAY)
    start(conn, "R-1", "nothing")

    m = run_metrics(conn, "R-1")

    assert m.status == "failed" and m.verdict is None and m.links == 0
    assert m.failure is not None and "nothing" in m.failure


def test_metrics_of_an_unknown_run_are_refused(conn) -> None:
    with pytest.raises(LookupError):
        run_metrics(conn, "R-nope")


# --- cases ------------------------------------------------------------------------------------


def test_the_repository_cases_file_loads() -> None:
    cases = load_cases(CASES)
    assert {case.id for case in cases} >= {"btk-ms-demo", "divarasib-2026-10"}


def test_the_demo_pair_is_a_btk_inhibitor_in_multiple_sclerosis() -> None:
    (demo,) = [case for case in load_cases(CASES) if case.set == "demo"]

    assert (demo.input.indication, demo.input.mechanism) == ("multiple sclerosis", "BTK inhibitor")
    assert demo.input.asset is None and demo.as_of is None  # a class, as of the day it is run
    assert demo.expected_top_risks and all(signal.url for signal in demo.signals)


def test_a_backtest_says_what_happened_next_and_is_dated_before_it() -> None:
    backtests = [case for case in load_cases(CASES) if case.set == "backtest"]

    assert backtests
    for case in backtests:
        assert case.outcome is not None and case.outcome.url and case.as_of is not None
        assert str(case.outcome.date) > str(case.as_of), case.id
        assert case.expected_verdict, case.id


def test_a_case_is_put_as_one_line_whatever_its_input_format() -> None:
    by_fields = EvalCase.model_validate(
        {"id": "a", "input": {"indication": "NSCLC", "mechanism": "KRAS G12C inhibitor"}}
    )
    by_text = EvalCase.model_validate({"id": "b", "input": {"query": " HRO761 in MSI-H "}})

    assert by_fields.input.text() == "KRAS G12C inhibitor for NSCLC"
    assert by_text.input.text() == "HRO761 in MSI-H"


@pytest.mark.parametrize(
    "text",
    [
        "- {id: a, input: {}}",
        "- {id: a, input: {asset: x}}\n- {id: a, input: {asset: y}}",
        "- {id: 'bad id', input: {asset: x}}",
        "- {id: a, input: {asset: x}, expected_verdict: [Maybe]}",
        "- {id: a, input: {asset: x}, surprise: 1}",
    ],
)
def test_a_malformed_cases_file_is_refused(tmp_path: Path, text: str) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)


# --- runner -----------------------------------------------------------------------------------


def test_a_verdict_inside_the_expectation_passes_and_one_outside_does_not(conn) -> None:
    cases = [
        case(id="in", expected_verdict=["Conditional", "Invest"]),
        case(id="out", expected_verdict=["Invest"]),
        case(id="open"),
    ]

    report = run_cases(conn, cases, start, mode="fixtures", today=TODAY)

    assert [c.verdict_as_expected for c in report.cases] == [True, False, None]
    assert all(c.runs[0].verdict == "Conditional" for c in report.cases)


def test_repeats_replayed_from_fixtures_are_not_called_stability(conn) -> None:
    report = run_cases(conn, [case()], start, mode="fixtures", repeat=3, today=TODAY)

    (result,) = report.cases
    assert len(result.runs) == 3 and len({r.run_id for r in result.runs}) == 3
    assert result.fresh_runs == 0
    assert result.same_verdict_every_run is None and result.top_risk_overlap is None
    assert "| replayed |" in summary(report)


def answered(conn: sqlite3.Connection, cache_hit: bool, extraction_cached: bool = False):
    """A fixture run that also logs its model calls: one extraction call and two reasoning
    calls, the reasoning fresh or served from the cache."""

    def run(connection: sqlite3.Connection, run_id: str, text: str):
        calls = [
            ("extraction", extraction_cached),
            ("reasoning.mechanism", cache_hit),
            ("reasoning.clinical", False),
        ]
        with connection:
            connection.executemany(
                "INSERT INTO llm_calls (run_id, step, cache_hit, cost_usd) VALUES (?, ?, ?, 0.01)",
                [(run_id, step, int(hit)) for step, hit in calls],
            )
        return start(connection, run_id, text)

    return run


def test_stability_is_measured_between_runs_a_model_answered_afresh(conn) -> None:
    fresh = run_cases(conn, [case()], answered(conn, False), mode="live", repeat=2, today=TODAY)
    cached = run_cases(conn, [case()], answered(conn, True), mode="live", repeat=2, today=TODAY)

    assert fresh.cases[0].fresh_runs == 2 and fresh.cases[0].same_verdict_every_run is True
    assert fresh.cases[0].top_risk_overlap == 1.0 and "| n/a | yes |" in summary(fresh)
    assert cached.cases[0].fresh_runs == 0 and cached.cases[0].same_verdict_every_run is None


def test_a_run_with_one_cached_reasoning_call_did_not_reason_afresh(conn) -> None:
    """It made fresh calls too (extraction, another module), which used to make it `fresh`."""
    report = run_cases(conn, [case()], answered(conn, True), mode="live", repeat=2, today=TODAY)

    run = report.cases[0].runs[0]
    assert run.llm_calls > run.cache_hits  # some call was fresh
    assert (run.reasoning_calls, run.reasoning_cache_hits) == (2, 1)
    assert report.cases[0].fresh_runs == 0 and "| replayed |" in summary(report)


def test_cached_extraction_does_not_hide_fresh_reasoning(conn) -> None:
    """The same bundle and new reasoning is exactly what stability of reasoning compares."""
    start_run = answered(conn, False, extraction_cached=True)

    report = run_cases(conn, [case()], start_run, mode="live", repeat=2, today=TODAY)

    assert report.cases[0].fresh_runs == 2 and report.cases[0].same_verdict_every_run is True


def test_a_single_run_says_nothing_about_stability(conn) -> None:
    (result,) = run_cases(conn, [case()], start, mode="fixtures", today=TODAY).cases
    assert result.same_verdict_every_run is None and result.top_risk_overlap is None


def test_a_case_runs_as_of_its_own_date(conn) -> None:
    cases = [case(id="early", as_of="2026-06-30"), case(id="today")]

    early, today = run_cases(conn, cases, start, mode="fixtures", today=TODAY).cases

    assert (early.as_of, today.as_of) == (date(2026, 6, 30), TODAY)
    assert early.runs[0].evidence == 10 and today.runs[0].evidence == 15


def test_a_case_that_cannot_run_is_reported_not_skipped(conn) -> None:
    missing = EvalCase.model_validate(
        {"id": "no-fixture", "input": {"asset": "HRO761"}, "expected_verdict": ["Conditional"]}
    )

    (result,) = run_cases(conn, [missing], start, mode="fixtures", today=TODAY).cases

    assert result.verdict_as_expected is None and result.runs[0].status == "failed"
    assert "hro761" in (result.runs[0].failure or "")
    assert "failed" in summary(run_cases(conn, [missing], start, mode="fixtures", today=TODAY))


def test_expected_risks_are_set_beside_the_closest_reported_one() -> None:
    reported = ["A link of the human translation chain is missing", "Crowded KRAS G12C class"]

    close, far = match_risks(["Competition in the KRAS G12C class", "Manufacturing"], reported)

    assert close.closest == "Crowded KRAS G12C class" and close.shared_words > 0.3
    assert far.shared_words == 0.0
    assert match_risks(["anything"], [])[0].closest is None


def test_the_report_is_written_as_json_and_a_readable_summary(conn, tmp_path: Path) -> None:
    cases = [case(expected_verdict=["Conditional"], expected_top_risks=["translation chain"])]
    report = run_cases(conn, cases, start, mode="fixtures", repeat=2, today=TODAY)

    write_report(report, tmp_path / "out" / "today")

    stored = json.loads((tmp_path / "out" / "today" / "results.json").read_text())
    text = (tmp_path / "out" / "today" / "summary.md").read_text()
    assert stored["mode"] == "fixtures" and len(stored["cases"][0]["runs"]) == 2
    assert "| c1 | Conditional | Conditional | yes | replayed |" in text
    assert "no model judged these reports" in text and "shared words only" in text
    assert "Verdicts: Conditional 2." in text


def test_a_backtest_puts_what_happened_next_beside_the_verdict(conn) -> None:
    case = EvalCase.model_validate(
        {
            "id": "back",
            "set": "backtest",
            "input": {"asset": "divarasib"},
            "as_of": "2026-06-30",
            "outcome": {
                "text": "it was approved",
                "url": "https://example.org/x",
                "date": "2026-12-01",
            },
        }
    )

    report = run_cases(conn, [case], start, mode="fixtures", today=date(2026, 10, 10))

    assert report.cases[0].set == "backtest" and report.cases[0].outcome is not None
    text = summary(report)
    assert "## What happened next" in text and "it was approved" in text
