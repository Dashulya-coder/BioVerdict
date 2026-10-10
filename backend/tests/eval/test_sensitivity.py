"""Sensitivity probes: a document is added to a finished run and code judges how far the run moved."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from bioverdict.api.schemas import (
    ClaimChange,
    ClaimSnapshot,
    DiffResponse,
    GateChange,
    RunSide,
)
from bioverdict.eval.cases import Probe, ProbeEvidence
from bioverdict.eval.sensitivity import NOISE_BAND, STRONG_MOVE, judge, run_probe
from bioverdict.llm import FakeLLM
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.pipeline.recompute import finish_recompute
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Basis,
    EvidenceLevel,
    GateId,
    Section,
    SourceKind,
    Verdict,
)
from bioverdict.store.runs_repo import create_run, load_claims

FIXTURES = Path(__file__).parents[3] / "fixtures"
EARLY = date(2026, 6, 30)
STATEMENT = (
    "The study met its primary and key secondary endpoint, with divarasib achieving clinically "
    "meaningful and statistically significant improvements in both progression-free survival "
    "(PFS) and overall survival (OS)."
)


def probe(kind: str = "strong", direction: str | None = "lower", **kw) -> Probe:
    document = ProbeEvidence(
        text=STATEMENT,
        url="https://www.roche.com/media/releases/med-cor-2026-07-02",
        source="Roche press release",
        source_kind=SourceKind.COMPANY,
        level=EvidenceLevel.HUMAN_INTERVENTIONAL,
        published_at=date(2026, 6, 15),
    )
    return Probe(kind=kind, direction=direction, evidence=document, **kw)


def side(verdict: Verdict = Verdict.CONDITIONAL, confidence: float = 0.7) -> RunSide:
    return RunSide(
        run_id="R",
        as_of=EARLY,
        bundle_version=1,
        content_hash="sha256:x",
        evidence_count=3,
        verdict=verdict,
        confidence=confidence,
        translation_chain_probability=0.1,
    )


def snap(confidence: float, critical: bool = False) -> ClaimSnapshot:
    return ClaimSnapshot(
        id="C-1", basis=Basis.EXTRACTED, confidence=confidence, gate_signals=[], critical=critical
    )


def moved(before: float, after: float, critical: bool = False) -> ClaimChange:
    return ClaimChange(
        change="changed",
        section=Section.CLINICAL,
        text="a claim",
        before=snap(before, critical),
        after=snap(after, critical),
        new_evidence_ids=[],
    )


def diff(base=None, head=None, claims=(), gates=()) -> DiffResponse:
    base, head = base or side(), head or side()
    return DiffResponse(
        base=base,
        head=head,
        verdict_changed=base.verdict != head.verdict,
        gates=list(gates),
        chain=[],
        evidence_added=[],
        evidence_removed=[],
        claims=list(claims),
        unchanged_claims=0,
        matching="",
    )


def test_a_probe_needs_a_direction_unless_it_is_noise() -> None:
    with pytest.raises(ValidationError, match="needs a direction"):
        probe("strong", None)
    with pytest.raises(ValidationError, match="no direction"):
        probe("noise", "lower")


# --- strong -------------------------------------------------------------------------------


def test_a_decisive_document_passes_when_the_verdict_moves_the_stated_way() -> None:
    ok, why = judge(probe(), diff(head=side(Verdict.DO_NOT_INVEST)))
    assert ok and "Conditional -> Do Not Invest" in why


def test_a_decisive_document_that_moves_the_verdict_the_wrong_way_fails() -> None:
    ok, _ = judge(probe(), diff(head=side(Verdict.INVEST)))
    assert not ok


def test_when_the_verdict_cannot_move_a_key_claim_must() -> None:
    key = moved(0.9, 0.9 - STRONG_MOVE - 0.01, critical=True)
    assert judge(probe(), diff(claims=[key]))[0]
    side_claim = moved(0.9, 0.5, critical=False)
    assert not judge(probe(), diff(claims=[side_claim]))[0]
    small = moved(0.9, 0.9 - STRONG_MOVE + 0.05, critical=True)
    assert not judge(probe(), diff(claims=[small]))[0]


def test_a_gate_that_newly_fires_counts_for_a_decisive_lowering_document() -> None:
    fired = GateChange(gate_id=GateId.K1, kind="hard", fired_before=False, fired_after=True)
    assert judge(probe(), diff(gates=[fired]))[0]
    cleared = GateChange(gate_id=GateId.S1, kind="soft", fired_before=True, fired_after=False)
    assert judge(probe(direction="higher"), diff(gates=[cleared]))[0]
    assert not judge(probe(direction="higher"), diff(gates=[fired]))[0]


# --- weak ---------------------------------------------------------------------------------


def test_a_minor_document_may_lower_confidence_but_not_flip_the_verdict() -> None:
    weak = probe("weak", "lower")
    assert judge(weak, diff(claims=[moved(0.8, 0.7)]))[0]
    assert judge(weak, diff(head=side(confidence=0.6)))[0]
    flipped = judge(weak, diff(head=side(Verdict.DO_NOT_INVEST), claims=[moved(0.8, 0.7)]))
    assert not flipped[0] and "flipped" in flipped[1]
    assert not judge(weak, diff())[0]  # it moved nothing
    assert not judge(weak, diff(claims=[moved(0.7, 0.8)]))[0]  # the wrong way


# --- noise --------------------------------------------------------------------------------


def test_an_irrelevant_document_changes_nothing() -> None:
    noise = probe("noise", None)
    assert judge(noise, diff())[0]
    assert judge(noise, diff(claims=[moved(0.7, 0.7 + NOISE_BAND / 2)]))[0]
    assert not judge(noise, diff(claims=[moved(0.7, 0.8)]))[0]
    assert not judge(noise, diff(head=side(Verdict.DO_NOT_INVEST)))[0]
    added = ClaimChange(
        change="added",
        section=Section.CLINICAL,
        text="new",
        before=None,
        after=snap(0.5),
        new_evidence_ids=[],
    )
    assert not judge(noise, diff(claims=[added]))[0]


def test_the_drift_of_time_on_a_chain_link_is_not_a_change_of_its_status() -> None:
    from bioverdict.api.schemas import ChainLinkChange
    from bioverdict.store.models import ChainLink

    drift = ChainLinkChange(
        link=ChainLink.PATIENT_BENEFIT,
        status_before="supported",
        status_after="supported",
        confidence_before=0.759,
        confidence_after=0.751,
    )
    flip = drift.model_copy(update={"status_after": "weak"})
    noise = probe("noise", None)

    assert judge(noise, diff().model_copy(update={"chain": [drift]}))[0]
    assert not judge(noise, diff().model_copy(update={"chain": [flip]}))[0]


# --- through the recompute -------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, EARLY)
    assert run_fixture(connection, "R-1", "divarasib", FIXTURES) is not None
    yield connection
    connection.close()


def finisher(answer: dict):
    def finish(conn: sqlite3.Connection, run_id: str) -> object:
        llm = FakeLLM(
            {"reasoning.classify": answer, "chair": {"questions": []}, "judge": {"judgments": []}}
        )
        return finish_recompute(conn, run_id, lambda: load_bundle(conn, run_id), lambda: llm)

    return finish


def test_a_document_that_bears_on_nothing_passes_as_noise(conn) -> None:
    result = run_probe(
        conn,
        "R-1",
        probe("noise", None, as_of=date(2026, 10, 7)),
        finisher({"links": []}),
        "R-probe",
    )

    assert result.passed is True and result.run_id == "R-probe"
    assert result.claims_moved == 0 and result.verdict_before == result.verdict_after


def test_a_document_that_contradicts_a_key_claim_passes_as_strong(conn) -> None:
    claims, _ = load_claims(conn, "R-1")
    key = next(c for c in claims if c.text.startswith("In the Phase 1 study divarasib"))
    link = {
        "claim_id": key.id,
        "evidence_id": "E-0014",
        "direction": "contradicts",
        "quote": "The study met its primary and key secondary endpoint",
    }

    result = run_probe(
        conn,
        "R-1",
        probe("strong", "lower", as_of=date(2026, 10, 7)),
        finisher({"links": [link]}),
        "R-probe",
    )

    assert result.claims_moved == 1
    assert result.passed is True, result.reason
    assert result.confidence_after is not None


def test_a_document_dated_after_the_cutoff_cannot_be_added_and_says_so(conn) -> None:
    late = probe("noise", None, as_of=date(2026, 6, 30)).model_copy()
    late.evidence = late.evidence.model_copy(update={"published_at": date(2026, 7, 2)})

    result = run_probe(conn, "R-1", late, finisher({"links": []}), "R-probe")

    assert result.passed is None and "dated after the cutoff" in result.reason


def test_a_case_whose_run_did_not_finish_has_nothing_to_grow(conn) -> None:
    create_run(conn, "R-2", {"asset": "divarasib"}, EARLY)  # still running

    result = run_probe(conn, "R-2", probe(), finisher({"links": []}), "R-probe")

    assert result.passed is None and "did not finish" in result.reason


# --- through the runner ---------------------------------------------------------------------


def a_case(**kw):
    from bioverdict.eval.cases import EvalCase

    base = {
        "id": "div",
        "input": {"asset": "divarasib"},
        "as_of": EARLY,
        "set": "backtest",
        "outcome": {
            "text": "it was approved",
            "url": "https://example.org/x",
            "date": "2026-12-01",
        },
        "probes": [probe("noise", None, as_of=date(2026, 10, 7)).model_dump(mode="json")],
    }
    return EvalCase.model_validate(base | kw)


def start(conn: sqlite3.Connection, run_id: str, text: str) -> object:
    return run_fixture(conn, run_id, text.casefold(), FIXTURES)


def test_the_runner_judges_each_probe_and_reports_it(tmp_path: Path) -> None:
    from bioverdict.eval.runner import run_cases, summary

    conn = connect(tmp_path / "r.db")
    migrate(conn)

    report = run_cases(
        conn,
        [a_case()],
        start,
        mode="live",
        today=date(2026, 10, 10),
        recompute=finisher({"links": []}),
    )

    (result,) = report.cases[0].probes
    assert result.kind == "noise" and result.passed is True
    text = summary(report)
    assert "## Sensitivity" in text and "1 of 1 probes that ran passed" in text
    assert "## What happened next" in text and "it was approved" in text
    assert report.cases[0].set == "backtest"


def test_without_a_model_the_probes_are_listed_as_not_run(tmp_path: Path) -> None:
    from bioverdict.eval.runner import run_cases, summary

    conn = connect(tmp_path / "r.db")
    migrate(conn)

    report = run_cases(conn, [a_case()], start, mode="fixtures", today=date(2026, 10, 10))

    (result,) = report.cases[0].probes
    assert result.passed is None and "needs a model" in result.reason
    assert "0 of 0 probes that ran passed; 1 did not run" in summary(report)
