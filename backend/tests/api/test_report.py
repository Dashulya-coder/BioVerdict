import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bioverdict.api.report import (
    ItemNotFoundError,
    RunNotFoundError,
    RunNotReadyError,
    build_report,
    build_trace,
    chain_status,
    get_claim,
    get_evidence,
)
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import ChainLink, Section, SectionStatus, Verdict
from bioverdict.store.runs_repo import create_run

FIXTURES = Path(__file__).parents[3] / "fixtures"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "t.db")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, date(2026, 10, 7))
    run_fixture(connection, "R-1", "divarasib", FIXTURES)
    yield connection
    connection.close()


def test_the_executive_verdict_comes_first_and_is_complete(conn: sqlite3.Connection) -> None:
    report = build_report(conn, "R-1")

    assert report.executive.verdict is Verdict.CONDITIONAL
    assert 0 <= report.executive.confidence <= 1
    assert 1 <= len(report.executive.top_risks) <= 3
    assert report.executive.what_would_change_our_mind
    assert report.run.status == "done" and report.run.verdict == "Conditional"


def test_assumptions_of_the_resolver_reach_the_report(conn: sqlite3.Connection) -> None:
    assert any("targets" in a for a in build_report(conn, "R-1").assumptions)


def test_sections_list_claims_with_the_critical_ones_first(conn: sqlite3.Connection) -> None:
    sections = {s.section: s for s in build_report(conn, "R-1").sections}

    translation = sections[Section.TRANSLATION].claims
    assert translation[0].critical
    assert [c.critical for c in translation] == sorted(
        (c.critical for c in translation), reverse=True
    )
    assert sections[Section.MECHANISM].status is SectionStatus.FOUND


def test_a_section_that_was_not_searched_says_so_instead_of_vanishing(
    conn: sqlite3.Connection,
) -> None:
    sections = {s.section: s for s in build_report(conn, "R-1").sections}

    competition = sections[Section.COMPETITION]
    assert competition.status is SectionStatus.NOT_SEARCHED and competition.claims == []


def test_every_claim_link_points_at_evidence_with_its_source(conn: sqlite3.Connection) -> None:
    report = build_report(conn, "R-1")

    linked = [link for s in report.sections for c in s.claims for link in c.links]
    assert linked
    for link in linked:
        assert link.quote and link.url.startswith("http") and link.source
    response = next(c for s in report.sections for c in s.claims if "confirmed responses" in c.text)
    assert response.links[0].evidence_id == "E-0007"
    assert response.badge == "source_fact"


def test_a_gap_is_marked_unknown_and_carries_what_would_answer_it(conn: sqlite3.Connection) -> None:
    claims = [c for s in build_report(conn, "R-1").sections for c in s.claims]

    exposure = next(c for c in claims if c.chain_link is ChainLink.HUMAN_EXPOSURE)
    assert exposure.badge == "unknown" and exposure.diligence_type == "patient_level_data"
    assert exposure.links == []


def test_the_translation_chain_has_five_links_and_marks_the_missing_ones(
    conn: sqlite3.Connection,
) -> None:
    chain = {c.link: c for c in build_report(conn, "R-1").translation_chain}

    assert list(chain) == list(ChainLink)
    assert chain[ChainLink.HUMAN_EXPOSURE].status == "missing"
    assert chain[ChainLink.TARGET_ENGAGEMENT].status == "missing"
    assert chain[ChainLink.BIOLOGICAL_RESPONSE].status in {"supported", "weak"}
    assert chain[ChainLink.BIOLOGICAL_RESPONSE].claim_ids


@pytest.mark.parametrize(
    "confidence, status",
    [(None, "missing"), (0.39, "missing"), (0.4, "weak"), (0.69, "weak"), (0.7, "supported")],
)
def test_chain_status_thresholds(confidence: float | None, status: str) -> None:
    assert chain_status(confidence) == status


def test_sources_are_only_the_evidence_the_claims_quote(conn: sqlite3.Connection) -> None:
    report = build_report(conn, "R-1")

    cited = {link.evidence_id for s in report.sections for c in s.claims for link in c.links}
    assert {e.id for e in report.sources} == cited
    assert all(e.claim_ids for e in report.sources)
    assert report.bundle.evidence_count > len(report.sources)  # the bundle holds more than is cited


def test_the_bundle_identity_is_in_the_report(conn: sqlite3.Connection) -> None:
    bundle = build_report(conn, "R-1").bundle

    assert bundle.version == 1 and bundle.content_hash.startswith("sha256:")
    assert bundle.section_statuses[Section.COMPETITION] is SectionStatus.NOT_SEARCHED


def test_a_single_claim_and_a_single_evidence_can_be_fetched(conn: sqlite3.Connection) -> None:
    report = build_report(conn, "R-1")
    claim = next(c for s in report.sections for c in s.claims)

    assert get_claim(conn, "R-1", claim.id) == claim
    evidence = get_evidence(conn, "R-1", "E-0007")
    assert evidence.badge == "source_fact" and evidence.claim_ids


def test_unknown_items_are_reported_not_invented(conn: sqlite3.Connection) -> None:
    with pytest.raises(RunNotFoundError):
        build_report(conn, "R-missing")
    with pytest.raises(ItemNotFoundError):
        get_claim(conn, "R-1", "C-9999")
    with pytest.raises(ItemNotFoundError):
        get_evidence(conn, "R-1", "E-9999")


def test_a_run_that_is_still_going_has_no_report(conn: sqlite3.Connection) -> None:
    create_run(conn, "R-2", {}, date(2026, 10, 7))
    with pytest.raises(RunNotReadyError):
        build_report(conn, "R-2")


def test_the_trace_lists_the_steps_and_totals_the_model_calls(conn: sqlite3.Connection) -> None:
    trace = build_trace(conn, "R-1")

    assert trace.events[0].step == "resolve"
    assert trace.events[-1].step == "run" and trace.events[-1].status == "done"
    assert trace.totals.calls == 0 and trace.totals.cost_usd == 0  # a fixture run calls no model
