"""The sensitivity benchmark: a document is added to a finished run and the diff is checked."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.eval.sensitivity import SensitivityCase, load_cases, run_cases, summary
from bioverdict.llm import FakeLLM
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle
from bioverdict.store.runs_repo import create_run, load_claims

FIXTURES = Path(__file__).parents[3] / "fixtures"
EARLY = date(2026, 6, 30)
FULL = Bundle.model_validate_json((FIXTURES / "bundles" / "divarasib.json").read_text())
STATEMENT = FULL.evidence_by_id()["E-0005"]  # Roche, 2026-07-02: absent from the early run
QUOTE = "The study met its primary and key secondary endpoint"
NEW_ID = "E-0014"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "run.db")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, EARLY)
    assert run_fixture(connection, "R-1", "divarasib", FIXTURES) is not None
    yield connection
    connection.close()


def case(kind: str, module: str | None, direction: str) -> SensitivityCase:
    return SensitivityCase.model_validate(
        {
            "id": f"{kind}-case",
            "kind": kind,
            "item": "Roche media release 2026-07-02",
            "document": {
                "text": STATEMENT.excerpt,
                "url": STATEMENT.url,
                "source": STATEMENT.source,
                "source_kind": "company",
                "level": "human_interventional",
                "published_at": "2026-06-15",
            },
            "expect": {"module": module, "direction": direction},
        }
    )


def placing(conn, direction: str | None):
    claims, _ = load_claims(conn, "R-1")
    target = next(c for c in claims if c.text.startswith("In the Phase 1 study divarasib"))
    links = (
        [{"claim_id": target.id, "evidence_id": NEW_ID, "direction": direction, "quote": QUOTE}]
        if direction
        else []
    )
    answer = {"links": links, "new_claims": [], "unmatched": [] if direction else [NEW_ID]}
    return lambda _run: FakeLLM(
        {"reasoning.classify": answer, "chair": {"questions": []}, "judge": {"judgments": []}}
    )


def test_a_contradicting_document_lowers_its_module_and_is_named_as_the_cause(conn) -> None:
    report = run_cases(
        conn, "R-1", [case("strong", "clinical_development", "down")], placing(conn, "contradicts")
    )

    outcome = report.cases[0]
    assert outcome.passed and outcome.balance_after < outcome.balance_before
    assert "clinical_development" in outcome.moved_modules
    assert "1 of 1 case(s) passed" in summary(report)


def test_a_case_fails_when_the_module_moves_the_other_way(conn) -> None:
    report = run_cases(
        conn, "R-1", [case("strong", "clinical_development", "down")], placing(conn, "supports")
    )

    assert not report.cases[0].passed and "expected down" in report.cases[0].reason


def test_noise_passes_only_when_no_module_moves(conn) -> None:
    quiet = run_cases(conn, "R-1", [case("noise", None, "none")], placing(conn, None))
    assert quiet.cases[0].passed and quiet.cases[0].reason == "no module moved"


def test_noise_that_moves_a_module_fails(conn) -> None:
    loud = run_cases(conn, "R-1", [case("noise", None, "none")], placing(conn, "contradicts"))
    assert not loud.cases[0].passed and "clinical_development" in loud.cases[0].reason


def test_a_case_that_cannot_be_added_is_reported_not_run(conn) -> None:
    outcome = run_cases(
        conn, "R-none", [case("strong", "clinical_development", "down")], placing(conn, None)
    ).cases[0]

    assert not outcome.passed and outcome.reason.startswith("not run:")


def test_the_cases_file_of_the_repository_loads() -> None:
    cases = load_cases(FIXTURES.parent / "eval" / "sensitivity.yaml")
    assert {c.kind for c in cases} == {"strong", "weak", "noise"}
