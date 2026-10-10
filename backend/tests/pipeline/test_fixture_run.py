import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.pipeline.fixture_run import fixture_names, run_fixture
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import ChainLink, Verdict
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    create_run,
    get_run,
    load_claims,
    load_events,
)

FIXTURES = Path(__file__).parents[3] / "fixtures"
AS_OF = date(2026, 10, 7)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    yield connection
    connection.close()


def start(conn: sqlite3.Connection, run_id: str = "R-1") -> None:
    create_run(conn, run_id, {"asset": "divarasib"}, AS_OF)


def test_the_divarasib_fixture_is_complete() -> None:
    assert "divarasib" in fixture_names(FIXTURES)


def test_a_fixture_run_finishes_with_a_verdict_and_its_records(conn: sqlite3.Connection) -> None:
    start(conn)

    result = run_fixture(conn, "R-1", "divarasib", FIXTURES)

    run = get_run(conn, "R-1")
    assert result is not None and run is not None
    assert run.status == DONE and run.result == result
    assert run.verdict == result.verdict.value
    assert run.resolver is not None and run.resolver.targets[0].symbol == "KRAS"
    assert load_bundle(conn, "R-1").run_id == "R-1"
    assert load_claims(conn, "R-1")[0]


def test_a_thin_translation_chain_keeps_the_verdict_below_invest(conn: sqlite3.Connection) -> None:
    start(conn)

    result = run_fixture(conn, "R-1", "divarasib", FIXTURES)

    assert result is not None and result.verdict is Verdict.CONDITIONAL
    assert any(g.gate_id.value == "S1" and g.fired for g in result.gates)


def test_every_quote_of_the_fixture_survives_grounding(conn: sqlite3.Connection) -> None:
    start(conn)
    run_fixture(conn, "R-1", "divarasib", FIXTURES)

    detail = [
        e.detail for e in load_events(conn, "R-1") if e.step == "reason" and e.status == "done"
    ]
    assert detail and "0 dropped" in detail[0]


def test_every_chain_link_is_spoken_to_and_missing_ones_are_unknown(
    conn: sqlite3.Connection,
) -> None:
    start(conn)
    run_fixture(conn, "R-1", "divarasib", FIXTURES)

    claims, _ = load_claims(conn, "R-1")

    assert {c.chain_link for c in claims if c.chain_link} == set(ChainLink)
    exposure = next(c for c in claims if c.chain_link is ChainLink.HUMAN_EXPOSURE)
    assert exposure.basis.value == "unknown" and exposure.diligence_type is not None


def test_the_progress_log_follows_the_pipeline_steps(conn: sqlite3.Connection) -> None:
    start(conn)
    run_fixture(conn, "R-1", "divarasib", FIXTURES)

    events = load_events(conn, "R-1")

    steps = [(e.step, e.status) for e in events]
    assert steps == [
        ("resolve", "started"),
        ("resolve", "done"),
        ("collect", "started"),
        ("collect", "done"),
        ("freeze", "started"),
        ("freeze", "done"),
        ("reason", "started"),
        ("reason", "done"),
        ("skeptic", "started"),
        ("skeptic", "done"),
        ("verify", "started"),
        ("verify", "done"),
        ("score", "started"),
        ("score", "done"),
        ("chair", "started"),
        ("chair", "done"),
        ("run", "done"),
    ]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


def test_an_unknown_asset_fails_the_run_and_says_what_exists(conn: sqlite3.Connection) -> None:
    start(conn)

    result = run_fixture(conn, "R-1", "no-such-drug", FIXTURES)

    run = get_run(conn, "R-1")
    assert result is None and run is not None and run.status == FAILED
    last = load_events(conn, "R-1")[-1]
    assert (last.step, last.status) == ("run", "failed")
    assert "no-such-drug" in last.detail and "divarasib" in last.detail


def test_the_asset_name_is_case_insensitive(conn: sqlite3.Connection) -> None:
    start(conn)
    assert run_fixture(conn, "R-1", "  Divarasib ", FIXTURES) is not None


def test_the_fixture_verdict_carries_pos_but_no_rnpv_without_market_records(
    conn: sqlite3.Connection,
) -> None:
    start(conn)

    result = run_fixture(conn, "R-1", "divarasib", FIXTURES)

    assert result is not None and result.pos is not None
    assert result.rnpv is None  # the fixture has no epidemiology or price records
