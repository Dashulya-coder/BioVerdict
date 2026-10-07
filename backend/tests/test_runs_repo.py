import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Basis,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    ConfidenceParts,
    Direction,
    GateId,
    Indication,
    ResolverOutput,
    Section,
    ServiceFlag,
    Target,
    Verdict,
    VerdictResult,
)
from bioverdict.store.runs_repo import (
    DONE,
    RUNNING,
    add_event,
    create_run,
    finish_run,
    get_run,
    list_runs,
    load_claims,
    load_events,
    save_claims,
    save_resolver,
)

AS_OF = date(2026, 10, 7)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    yield connection
    connection.close()


def test_a_new_run_is_running_and_remembers_its_input(conn: sqlite3.Connection) -> None:
    create_run(conn, "R-1", {"asset": "divarasib"}, AS_OF)

    run = get_run(conn, "R-1")

    assert run is not None
    assert (run.status, run.input, run.as_of) == (RUNNING, {"asset": "divarasib"}, AS_OF)
    assert run.verdict is None and run.result is None and run.finished_at is None


def test_an_unknown_run_is_none(conn: sqlite3.Connection) -> None:
    assert get_run(conn, "R-missing") is None


def test_a_finished_run_keeps_the_verdict_and_the_full_result(conn: sqlite3.Connection) -> None:
    create_run(conn, "R-1", {}, AS_OF)
    result = VerdictResult(
        verdict=Verdict.CONDITIONAL, confidence=0.42, top_risks=["a thin translation chain"]
    )

    finish_run(conn, "R-1", DONE, result)

    run = get_run(conn, "R-1")
    assert run is not None and run.status == DONE and run.finished_at is not None
    assert run.verdict == "Conditional"
    assert run.result == result


def test_the_resolver_output_with_its_assumptions_is_kept(conn: sqlite3.Connection) -> None:
    create_run(conn, "R-1", {}, AS_OF)
    resolver = ResolverOutput(
        indication=Indication(name="NSCLC", mondo_id="MONDO_0005233"),
        targets=[Target(symbol="KRAS", ensembl="ENSG00000133703")],
        assumptions=["targets: not stated in the input, filled in by the model"],
    )

    save_resolver(conn, "R-1", resolver)

    run = get_run(conn, "R-1")
    assert run is not None and run.resolver == resolver


def test_runs_are_listed_newest_first(conn: sqlite3.Connection) -> None:
    for run_id in ("R-1", "R-2", "R-3"):
        create_run(conn, run_id, {}, AS_OF)
    assert [r.run_id for r in list_runs(conn)] == ["R-3", "R-2", "R-1"]
    assert [r.run_id for r in list_runs(conn, limit=2)] == ["R-3", "R-2"]


def test_events_are_numbered_per_run_in_order(conn: sqlite3.Connection) -> None:
    add_event(conn, "R-1", "collect", "started")
    add_event(conn, "R-1", "collect", "done", "86 evidence")
    add_event(conn, "R-2", "collect", "started")

    events = load_events(conn, "R-1")

    assert [(e.seq, e.step, e.status, e.detail) for e in events] == [
        (1, "collect", "started", ""),
        (2, "collect", "done", "86 evidence"),
    ]
    assert [e.seq for e in load_events(conn, "R-2")] == [1]


def test_events_can_be_read_from_a_point_on(conn: sqlite3.Connection) -> None:
    for step in ("resolve", "collect", "freeze"):
        add_event(conn, "R-1", step, "done")
    assert [e.step for e in load_events(conn, "R-1", after_seq=1)] == ["collect", "freeze"]
    assert load_events(conn, "R-1", after_seq=3) == []


def make_claim(claim_id: str, **overrides) -> Claim:
    fields = {
        "id": claim_id,
        "run_id": "R-1",
        "section": Section.TRANSLATION,
        "text": "Divarasib produces confirmed responses in NSCLC patients",
        "claim_type": ClaimType.DRUG_ACTS_IN_HUMANS,
        "basis": Basis.EXTRACTED,
        "confidence": 0.72,
        "confidence_parts": ConfidenceParts(support=0.8, contra=0.1, freshness=0.9),
        "flags": [ServiceFlag.CONTESTED],
        "depends_on": ["C-0001"],
        "chain_link": ChainLink.BIOLOGICAL_RESPONSE,
        "gate_signals": [GateId.K4],
        "critical": True,
    }
    return Claim(**{**fields, **overrides})


def test_claims_and_their_links_survive_storage_unchanged(conn: sqlite3.Connection) -> None:
    claims = [
        make_claim("C-0001"),
        make_claim("C-0002", confidence_parts=None, flags=[], gate_signals=[], critical=False),
    ]
    links = [
        ClaimEvidenceLink(
            claim_id="C-0001", evidence_id="E-0007", direction=Direction.SUPPORTS, quote="53.4%"
        )
    ]

    save_claims(conn, "R-1", claims, links, version=1)
    loaded_claims, loaded_links = load_claims(conn, "R-1")

    assert loaded_claims == claims
    assert loaded_links == links


def test_claims_are_scoped_to_their_run(conn: sqlite3.Connection) -> None:
    save_claims(conn, "R-1", [make_claim("C-0001")], [], version=1)
    save_claims(conn, "R-2", [make_claim("C-0001", run_id="R-2")], [], version=1)

    assert [c.run_id for c in load_claims(conn, "R-1")[0]] == ["R-1"]
    assert [c.run_id for c in load_claims(conn, "R-2")[0]] == ["R-2"]
    assert load_claims(conn, "R-3") == ([], [])
