"""The sensitivity benchmark: a document is added to a finished run and the diff is checked."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.api.diff import build_diff
from bioverdict.eval.sensitivity import SensitivityCase, load_cases, run_cases, summary
from bioverdict.llm import FakeLLM
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle
from bioverdict.store.runs_repo import create_run, get_run, load_claims

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
        {
            "reasoning.classify": answer,
            "chair": {"questions": []},
            "synthesis": {"theses": []},
            "judge": {"judgments": []},
        }
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


def _module_diff(*, answer_after: str, with_cause: bool):
    """A diff in which the unmet-need module changes its answer, with or without a new cause."""
    from bioverdict.api.schemas import DiffResponse, ModuleCause, ModuleChange, RunSide
    from bioverdict.scoring.module_answers import ModuleAnswer, ModuleId
    from bioverdict.store.models import Direction, EvidenceLevel, Verdict

    cause = ModuleCause(
        evidence_id="E-0014",
        source="s",
        url="https://example.org",
        published_at=None,
        level=EvidenceLevel.HUMAN_INTERVENTIONAL,
        direction=Direction.SUPPORTS,
        quote="q",
        claim_id="C-1",
        claim_text="t",
        claim_change="changed",
        confidence_before=0.5,
        confidence_after=0.6,
        contribution_before=None,
        contribution_after=0.1,
    )
    module = ModuleChange(
        module=ModuleId.UNMET_NEED,
        title="Disease and unmet need",
        answer_before=ModuleAnswer.SUPPORTS,
        answer_after=ModuleAnswer(answer_after),
        balance_before=1.0,
        balance_after=None,
        headline_before="",
        headline_after="",
        changed=True,
        causes=[cause] if with_cause else [],
    )
    side = RunSide(
        run_id="R",
        as_of=EARLY,
        bundle_version=1,
        content_hash="sha256:x",
        evidence_count=1,
        verdict=Verdict.CONDITIONAL,
        confidence=0.5,
        translation_chain_probability=0.1,
    )
    from bioverdict.api.schemas import EvidenceView

    added = EvidenceView.model_construct(id="E-0014")
    return DiffResponse(
        base=side,
        head=side,
        verdict_changed=False,
        modules=[module],
        gates=[],
        chain=[],
        evidence_added=[added],
        evidence_removed=[],
        claims=[],
        unchanged_claims=0,
        matching="",
    )


def test_noise_fails_when_an_answer_flips_with_or_without_a_cause() -> None:
    """The strict rule: the diff is against a control at the same cutoff, so there is no drift
    that could excuse a changed answer."""
    from bioverdict.eval.sensitivity import judge_case

    noise = case("noise", None, "none")

    ok, why = judge_case(noise, _module_diff(answer_after="insufficient", with_cause=False))
    assert not ok and "disease_unmet_need" in why

    ok, why = judge_case(noise, _module_diff(answer_after="insufficient", with_cause=True))
    assert not ok and "disease_unmet_need" in why


# --- the control: the base run at the case's cutoff, with no document --------------------------------

LATE = date(2026, 10, 7)
PASSIVE = {
    "chair": {"questions": []},
    "synthesis": {"theses": []},
    "judge": {"judgments": []},
}  # and no classification


def test_a_later_cutoff_is_not_mistaken_for_the_effect_of_the_document(conn) -> None:
    noise = case("noise", None, "none").model_copy(update={"as_of": LATE})

    report = run_cases(conn, "R-1", [noise], placing(conn, None))

    outcome = report.cases[0]
    assert outcome.passed and outcome.reason == "no module moved"
    # Against the base the same run does drift, because the claims aged to the later cutoff.
    # That is what the old comparison mistook for an effect, and what the control removes.
    base_claims = {c.id: c.confidence for c in load_claims(conn, "R-1")[0]}
    aged = {c.id: c.confidence for c in load_claims(conn, outcome.run_id)[0]}
    assert any(aged[i] != base_claims[i] for i in base_claims)


def test_the_control_is_the_base_at_the_same_cutoff_made_once_without_asking_the_model(
    conn,
) -> None:
    runs: list[str] = []

    def llm(run_id: str) -> FakeLLM:
        runs.append(run_id)
        if len(runs) == 1:  # the control: a model with no classification to give must not be asked
            return FakeLLM(PASSIVE)
        return placing(conn, "contradicts")(run_id)

    report = run_cases(
        conn,
        "R-1",
        [case("strong", "clinical_development", "down"), case("noise", None, "none")],
        llm,
    )

    control = runs[0]
    assert len(runs) == 3  # one control, then one run for each case
    assert report.controls == {EARLY.isoformat(): control}
    assert [c.control_run for c in report.cases] == [control, control]
    assert get_run(conn, control).status == "done"
    assert len(load_bundle(conn, control).evidence) == len(load_bundle(conn, "R-1").evidence)
    assert [c.text for c in load_claims(conn, control)[0]] == [
        c.text for c in load_claims(conn, "R-1")[0]
    ]
    assert f"Control at {EARLY.isoformat()}: run {control}" in summary(report)


def test_every_case_is_read_against_its_control_not_against_the_base(conn) -> None:
    report = run_cases(
        conn, "R-1", [case("strong", "clinical_development", "down")], placing(conn, "contradicts")
    )

    outcome = report.cases[0]
    diff = build_diff(conn, outcome.control_run, outcome.run_id)
    target = next(m for m in diff.modules if m.module.value == "clinical_development")
    assert (outcome.balance_before, outcome.balance_after) == (
        target.balance_before,
        target.balance_after,
    )
    assert outcome.verdict_before == diff.base.verdict.value


def test_a_control_that_cannot_be_made_is_reported_and_no_case_runs(conn) -> None:
    case_ = case("strong", "clinical_development", "down").model_copy(
        update={"as_of": date(2020, 1, 1)}  # before the base run's cutoff
    )

    outcome = run_cases(conn, "R-1", [case_], placing(conn, None)).cases[0]

    assert not outcome.passed and outcome.run_id is None
    assert outcome.reason.startswith("not run:") and "earlier" in outcome.reason
