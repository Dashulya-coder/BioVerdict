"""Recompute on added evidence: a new run with the next bundle version; the original is untouched.

The original is the divarasib fixture as of 2026-06-30. The added item is the real Roche
statement of 2026-07-02 from the same fixture, and the model's drafts are the fixture's, with
their evidence ids rewritten to the ids of the new bundle.
"""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.api.diff import build_diff
from bioverdict.llm import ConfigError, FakeLLM
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.pipeline.recompute import (
    PARENT,
    RecomputeError,
    analyst_evidence,
    finish_recompute,
    prepare_recompute,
)
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle, Evidence, EvidenceLevel, SourceKind
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    create_run,
    get_run,
    list_runs,
    load_claims,
    load_events,
)

FIXTURES = Path(__file__).parents[3] / "fixtures"
EARLY, LATE = date(2026, 6, 30), date(2026, 10, 7)
FULL = Bundle.model_validate_json(
    (FIXTURES / "bundles" / "divarasib.json").read_text(encoding="utf-8")
)
# Published 2026-07-02: absent from the run as of 2026-06-30, and E-0005 in the full fixture.
STATEMENT = FULL.evidence_by_id()["E-0005"].model_copy(update={"id": "added-1"})
NEW_ID = "E-0014"  # the early run holds ten items, the last of them E-0013


def drafts() -> dict:
    """The fixture's drafts as a model would write them over the new bundle: the statement is
    cited under its new id, and what the bundle does not hold is cited in vain."""
    absent = {"E-0003", "E-0006", "E-0014", "E-0015"}

    def rewrite(found: re.Match[str]) -> str:
        if found.group() == "E-0005":
            return NEW_ID
        return "E-9999" if found.group() in absent else found.group()

    text = (FIXTURES / "reasoning" / "divarasib.json").read_text(encoding="utf-8")
    return json.loads(re.sub(r"E-\d{4}", rewrite, text))


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "run.db")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, EARLY)
    assert run_fixture(connection, "R-1", "divarasib", FIXTURES) is not None
    yield connection
    connection.close()


def recompute(conn: sqlite3.Connection, added: list[Evidence] | None = None, as_of=LATE):
    bundle = prepare_recompute(conn, "R-1", "R-2", added or [STATEMENT], as_of)
    return finish_recompute(conn, "R-2", lambda: bundle, lambda: FakeLLM(drafts()))


def test_added_evidence_becomes_the_next_bundle_version_of_a_new_run(conn) -> None:
    result = recompute(conn)

    run, bundle = get_run(conn, "R-2"), load_bundle(conn, "R-2")
    assert result is not None and run is not None and run.status == DONE
    assert run.input == {"asset": "divarasib", PARENT: "R-1"} and run.as_of == LATE
    assert (bundle.version, len(bundle.evidence)) == (2, 11)
    added = bundle.evidence_by_id()[NEW_ID]
    assert (added.excerpt, added.version) == (STATEMENT.excerpt, 2)


def test_the_original_run_and_its_bundle_stay_as_they_were(conn) -> None:
    before = (get_run(conn, "R-1"), load_bundle(conn, "R-1"), load_claims(conn, "R-1"))

    recompute(conn)

    assert (get_run(conn, "R-1"), load_bundle(conn, "R-1"), load_claims(conn, "R-1")) == before
    # The new run carries the original bundle as its version 1, hash and ids included.
    carried = load_bundle(conn, "R-2", version=1)
    assert carried.content_hash == before[1].content_hash
    assert [e.id for e in carried.evidence] == [e.id for e in before[1].evidence]


def test_the_new_run_keeps_the_resolved_input_and_says_where_it_came_from(conn) -> None:
    recompute(conn)

    original, run = get_run(conn, "R-1"), get_run(conn, "R-2")
    assert original is not None and run is not None and run.resolver == original.resolver
    events = [(e.step, e.status) for e in load_events(conn, "R-2")]
    assert events[:6] == [
        ("resolve", "started"),
        ("resolve", "done"),
        ("collect", "started"),
        ("collect", "done"),
        ("freeze", "started"),
        ("freeze", "done"),
    ]
    assert events[-1] == ("run", "done")
    assert "R-1" in load_events(conn, "R-2")[1].detail


def test_the_diff_names_the_added_evidence_and_the_claims_that_rest_on_it(conn) -> None:
    recompute(conn)

    diff = build_diff(conn, "R-1", "R-2")

    assert (diff.base.bundle_version, diff.head.bundle_version) == (1, 2)
    assert [e.id for e in diff.evidence_added] == [NEW_ID] and diff.evidence_removed == []
    resting = [c for c in diff.claims if c.new_evidence_ids]
    assert resting and all(c.change == "added" and c.before is None for c in resting)
    assert all(c.new_evidence_ids == [NEW_ID] for c in resting)
    assert any("progression-free" in c.text for c in resting)


@pytest.mark.parametrize(
    "added,as_of,reason",
    [
        ([FULL.evidence_by_id()["E-0007"]], LATE, "already in the bundle"),
        ([STATEMENT, STATEMENT], LATE, "repeat each other"),
        ([STATEMENT], EARLY, "dated after the cutoff"),
        ([STATEMENT], date(2026, 1, 1), "earlier than the original"),
    ],
)
def test_a_request_that_adds_nothing_is_refused_and_leaves_no_run(
    conn, added, as_of, reason
) -> None:
    with pytest.raises(RecomputeError, match=reason):
        prepare_recompute(conn, "R-1", "R-2", added, as_of)

    assert [run.run_id for run in list_runs(conn)] == ["R-1"]


def test_only_a_finished_run_can_grow(conn) -> None:
    create_run(conn, "R-going", {"asset": "divarasib"}, EARLY)

    with pytest.raises(RecomputeError, match="finished"):
        prepare_recompute(conn, "R-going", "R-2", [STATEMENT], LATE)
    with pytest.raises(LookupError):
        prepare_recompute(conn, "R-nope", "R-2", [STATEMENT], LATE)


def test_a_model_failure_is_recorded_on_the_new_run_only(conn) -> None:
    bundle = prepare_recompute(conn, "R-1", "R-2", [STATEMENT], LATE)

    assert finish_recompute(conn, "R-2", lambda: bundle, lambda: FakeLLM({})) is None

    failed, original = get_run(conn, "R-2"), get_run(conn, "R-1")
    assert failed is not None and failed.status == FAILED
    assert original is not None and original.status == DONE
    assert load_events(conn, "R-2")[-1].detail == "KeyError"


def test_evidence_typed_in_by_an_analyst_is_marked_as_such() -> None:
    item = analyst_evidence(
        1,
        "  The study met its primary endpoint.  ",
        "https://www.example.org/news/1",
        " Example Journal ",
        SourceKind.COMPANY,
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        date(2026, 7, 2),
    )

    assert (item.source, item.excerpt) == ("Example Journal", "The study met its primary endpoint.")
    assert (item.source_family, item.independence_group) == (
        "analyst_added",
        "added:www.example.org",
    )
    assert (item.source_kind, item.level) == (
        SourceKind.COMPANY,
        EvidenceLevel.HUMAN_INTERVENTIONAL,
    )


def test_a_recompute_without_a_model_fails_with_the_reason_instead_of_hanging(conn) -> None:
    bundle = prepare_recompute(conn, "R-1", "R-2", [STATEMENT], LATE)

    def no_model():
        raise ConfigError("ANTHROPIC_API_KEY is not set")

    assert finish_recompute(conn, "R-2", lambda: bundle, no_model) is None

    run = get_run(conn, "R-2")
    assert run is not None and run.status == FAILED
    assert "ANTHROPIC_API_KEY" in load_events(conn, "R-2")[-1].detail


def test_a_recompute_that_cannot_be_prepared_is_failed_not_left_running(conn, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("bioverdict.pipeline.recompute.freeze", broken)

    with pytest.raises(sqlite3.OperationalError):
        prepare_recompute(conn, "R-1", "R-2", [STATEMENT], LATE)

    run = get_run(conn, "R-2")
    assert run is not None and run.status == FAILED
    assert load_events(conn, "R-2")[-1].detail == "OperationalError"


def test_a_claim_that_quotes_other_words_of_the_same_evidence_has_changed(conn) -> None:
    create_run(conn, "R-same", {"asset": "divarasib"}, EARLY)
    run_fixture(conn, "R-same", "divarasib", FIXTURES)
    assert build_diff(conn, "R-1", "R-same").claims == []
    link = conn.execute(
        "SELECT claim_id, evidence_id, quote FROM claim_evidence WHERE run_id = 'R-same' LIMIT 1"
    ).fetchone()
    with conn:
        conn.execute(
            "UPDATE claim_evidence SET quote = ? WHERE run_id = 'R-same' AND claim_id = ? "
            "AND evidence_id = ?",
            (link["quote"][:-1], link["claim_id"], link["evidence_id"]),
        )

    (changed,) = build_diff(conn, "R-1", "R-same").claims

    assert changed.change == "changed" and changed.after is not None
    assert changed.after.id == link["claim_id"]
