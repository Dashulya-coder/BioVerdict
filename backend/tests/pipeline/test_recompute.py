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
from bioverdict.api.report import build_report, get_claim
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
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    Evidence,
    EvidenceLevel,
    GateId,
    SourceKind,
    VerificationCheck,
)
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    create_run,
    get_run,
    list_runs,
    load_claims,
    load_events,
)
from bioverdict.store.verification_repo import load_checks, save_checks

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
    return finish_recompute(conn, "R-2", lambda: bundle, lambda: FakeLLM(drafts()), "full")


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


# --- the default mode: the model places the new evidence, code recomputes --------------------------

# A document dated before the original run's cutoff, recomputed at the same cutoff: the only thing
# that differs between the two runs is the document (a later cutoff would also age every claim).
DOC = STATEMENT.model_copy(update={"published_at": date(2026, 6, 15)})
QUOTE = "The study met its primary and key secondary endpoint"


def classified(conn, answer: dict):
    bundle = prepare_recompute(conn, "R-1", "R-2", [DOC], EARLY)
    return finish_recompute(
        conn,
        "R-2",
        lambda: bundle,
        lambda: FakeLLM(
            {
                "reasoning.classify": answer,
                "chair": {"questions": []},
                "synthesis": {"theses": []},
                "judge": {"judgments": []},
            }
        ),
    )


def key_claim(conn):
    claims, _ = load_claims(conn, "R-1")
    return claims, next(c for c in claims if c.text.startswith("In the Phase 1 study divarasib"))


def link_to(claim_id: str, direction: str, quote: str = QUOTE) -> dict:
    return {"claim_id": claim_id, "evidence_id": NEW_ID, "direction": direction, "quote": quote}


def test_placing_new_evidence_keeps_every_claim_as_it_was_and_moves_only_the_linked_one(
    conn,
) -> None:
    before, target = key_claim(conn)
    _, links_before = load_claims(conn, "R-1")

    result = classified(conn, {"links": [link_to(target.id, "contradicts")]})

    assert result is not None and get_run(conn, "R-2").status == DONE
    after, links_after = load_claims(conn, "R-2")
    assert [(c.id, c.text) for c in after] == [(c.id, c.text) for c in before]  # same claims
    moved = {a.id for a, b in zip(after, before, strict=True) if a.confidence != b.confidence}
    assert moved == {target.id}
    assert len(links_after) == len(links_before) + 1
    assert any(e.detail and "place 1 new item" in e.detail for e in load_events(conn, "R-2"))


def judged_links(conn, run_id: str) -> dict[tuple[str, str], str]:
    report = build_report(conn, run_id)
    return {
        (claim.id, link.evidence_id): link.judged
        for section in report.sections
        for claim in section.claims
        for link in claim.links
    }


def test_a_quote_the_judge_read_in_the_original_run_stays_read_in_the_recompute(conn) -> None:
    _, target = key_claim(conn)
    before = judged_links(conn, "R-1")
    read = {key for key, state in before.items() if state == "judged"}
    assert read  # the fixture run's judge confirmed some quotes

    classified(conn, {"links": [link_to(target.id, "contradicts")]})

    # The recompute asks the judge about the added document only: what it carried over keeps the
    # reading of the run it grew from, instead of showing as never read.
    after = judged_links(conn, "R-2")
    assert {key: after[key] for key in read} == dict.fromkeys(read, "judged")
    assert {key: after[key] for key in before} == before
    claim_id, evidence_id = next(iter(read))
    link = next(l for l in get_claim(conn, "R-2", claim_id).links if l.evidence_id == evidence_id)
    assert link.judged == "judged"


def test_a_claim_reworded_in_the_recompute_does_not_inherit_the_reading(conn) -> None:
    _, target = key_claim(conn)
    classified(conn, {"links": [link_to(target.id, "contradicts")]})
    claim_id, evidence_id = next(k for k, v in judged_links(conn, "R-1").items() if v == "judged")

    with conn:  # as a full recompute would: the same id, another claim
        conn.execute(
            "UPDATE claims SET text = text || ' (reworded)' WHERE run_id = 'R-2' AND id = ?",
            (claim_id,),
        )

    assert judged_links(conn, "R-2")[(claim_id, evidence_id)] == "not_judged"


def removal(claim_id: str) -> VerificationCheck:
    return VerificationCheck(
        claim_id=claim_id,
        check_name="entailment",
        passed=False,
        detail="E-0099 cited as supports, judged unrelated: the quote names another drug",
    )


def test_why_a_quote_was_removed_in_the_original_run_is_still_said_in_the_recompute(conn) -> None:
    _, target = key_claim(conn)
    other = next(c for c in load_claims(conn, "R-1")[0] if c.id != target.id)
    save_checks(conn, "R-1", [removal(other.id)])
    said = [(c.check, c.detail) for c in get_claim(conn, "R-1", other.id).checks]
    assert ("entailment", removal(other.id).detail) in said

    classified(conn, {"links": [link_to(target.id, "contradicts")]})

    # The recompute judged the new quote only; the claim it carried over lost that quote earlier.
    assert [(c.check, c.detail) for c in get_claim(conn, "R-2", other.id).checks] == said
    report = build_report(conn, "R-2")
    in_report = next(c for s in report.sections for c in s.claims if c.id == other.id)
    assert [(c.check, c.detail) for c in in_report.checks] == said


def test_a_reworded_claim_does_not_inherit_why_a_quote_was_removed(conn) -> None:
    _, target = key_claim(conn)
    other = next(c for c in load_claims(conn, "R-1")[0] if c.id != target.id)
    save_checks(conn, "R-1", [removal(other.id)])
    classified(conn, {"links": [link_to(target.id, "contradicts")]})

    with conn:
        conn.execute(
            "UPDATE claims SET text = text || ' (reworded)' WHERE run_id = 'R-2' AND id = ?",
            (other.id,),
        )

    details = [c.detail for c in get_claim(conn, "R-2", other.id).checks]
    assert removal(other.id).detail not in details


def test_the_diff_of_a_placed_document_names_only_the_claim_it_touches(conn) -> None:
    _, target = key_claim(conn)
    classified(conn, {"links": [link_to(target.id, "supports")]})

    diff = build_diff(conn, "R-1", "R-2")

    assert [e.id for e in diff.evidence_added] == [NEW_ID]
    assert [c.text for c in diff.claims] == [target.text] and diff.claims[0].change == "changed"
    assert diff.claims[0].new_evidence_ids == [NEW_ID]


def test_the_diff_says_which_module_the_document_moved_and_quotes_the_document(conn) -> None:
    _, target = key_claim(conn)  # a favourable clinical claim
    classified(conn, {"links": [link_to(target.id, "contradicts")]})

    modules = {m.module.value: m for m in build_diff(conn, "R-1", "R-2").modules}

    assert len(modules) == 6
    clinical = modules["clinical_development"]
    assert clinical.changed and clinical.balance_after < clinical.balance_before
    cause = clinical.causes[0]
    assert (cause.evidence_id, cause.claim_id, cause.quote) == (NEW_ID, target.id, QUOTE)
    assert cause.direction.value == "contradicts" and cause.claim_change == "changed"
    assert cause.confidence_after < cause.confidence_before
    assert cause.contribution_after < cause.contribution_before
    assert cause.url == DOC.url
    untouched = [m for name, m in modules.items() if name.startswith(("disease", "mechanism"))]
    assert all(not m.changed and m.causes == [] for m in untouched)
    # The claim is a key claim, so the verdict's own module names the same document.
    assert modules["investment_underwriting"].causes[0].evidence_id == NEW_ID


def test_a_document_that_bears_on_nothing_moves_no_module(conn) -> None:
    classified(conn, {"links": [], "unmatched": [NEW_ID]})

    modules = build_diff(conn, "R-1", "R-2").modules

    assert all(not m.changed and m.causes == [] for m in modules)


def test_a_new_fact_becomes_a_claim_numbered_after_the_existing_ones(conn) -> None:
    before, _ = key_claim(conn)
    fact = {
        "text": "The sponsor reports that the Phase 3 trial met its endpoints",
        "claim_type": "study_fact",
        "basis": "extracted",
        "links": [{"evidence_id": NEW_ID, "direction": "supports", "quote": QUOTE}],
    }
    classified(conn, {"links": [], "new_claims": [fact]})

    after, _ = load_claims(conn, "R-2")

    assert len(after) == len(before) + 1
    assert (
        after[-1].text.startswith("The sponsor reports") and after[-1].section.value == "clinical"
    )


def test_recompute_logs_and_removes_a_new_claim_with_a_failed_citation(conn) -> None:
    before, _ = load_claims(conn, "R-1")
    fact = {
        "text": "The model invented a finding",
        "claim_type": "other",
        "basis": "extracted",
        "links": [link_to("unused", "supports", "words that are not there")],
    }
    # Draft links have no claim id: code assigns the new claim's id.
    del fact["links"][0]["claim_id"]
    assert classified(conn, {"new_claims": [fact]}) is not None
    after, links = load_claims(conn, "R-2")
    assert [c.text for c in after] == [c.text for c in before]
    dropped = conn.execute(
        "SELECT claim_id FROM verification_log WHERE run_id = 'R-2' AND check_name = 'claim_dropped'"
    ).fetchall()
    assert len(dropped) == 1
    assert all(l.claim_id != dropped[0]["claim_id"] for l in links)


def test_an_invented_quote_places_nothing_and_the_run_still_finishes(conn) -> None:
    before, _ = key_claim(conn)

    result = classified(
        conn, {"links": [link_to(before[0].id, "supports", "words that are not there")]}
    )

    assert result is not None
    after, _ = load_claims(conn, "R-2")
    assert [c.confidence for c in after] == [c.confidence for c in before]
    checks = conn.execute(
        "SELECT check_name FROM verification_log WHERE run_id = 'R-2' "
        "AND check_name NOT IN ('source_authority', 'temporal_validity')"
    ).fetchall()
    assert [row["check_name"] for row in checks] == ["quote_in_source"]


def test_a_model_without_a_classification_fails_the_run_with_a_reason(conn) -> None:
    bundle = prepare_recompute(conn, "R-1", "R-2", [DOC], EARLY)

    assert finish_recompute(conn, "R-2", lambda: bundle, lambda: FakeLLM({})) is None
    assert get_run(conn, "R-2").status == FAILED


def test_the_environment_chooses_the_mode(monkeypatch) -> None:
    from bioverdict import settings

    monkeypatch.delenv("RECOMPUTE_MODE", raising=False)
    assert settings.recompute_mode() == "classify"
    monkeypatch.setenv("RECOMPUTE_MODE", "FULL")
    assert settings.recompute_mode() == "full"
    monkeypatch.setenv("RECOMPUTE_MODE", "nonsense")
    assert settings.recompute_mode() == "classify"


# --- a document that fills a missing link of the translation chain -----------------------------------

EXPOSURE_QUOTE = (
    "Plasma exposure of divarasib at the recommended dose exceeded the concentration that "
    "inhibited KRAS G12C signalling in the cell models."
)
ENGAGEMENT_QUOTE = "Paired tumour biopsies showed more than 90 percent occupancy of KRAS G12C."
PK_DOC = analyst_evidence(
    1,
    f"{EXPOSURE_QUOTE} {ENGAGEMENT_QUOTE}",
    "https://example.org/divarasib-pk",
    "Added by an analyst",
    SourceKind.PEER_REVIEWED,
    EvidenceLevel.HUMAN_INTERVENTIONAL,
    date(2026, 6, 15),
)


def chain_claim(link: str, text: str, quote: str) -> dict:
    return {
        "text": text,
        "claim_type": "drug_acts_in_humans",
        "basis": "extracted",
        "chain_link": link,
        "implication": "favourable",
        "links": [{"evidence_id": NEW_ID, "direction": "supports", "quote": quote}],
    }


EXPOSURE_CLAIM = chain_claim(
    "human_exposure",
    "Divarasib reaches an exposure in patients above the effective experimental one.",
    EXPOSURE_QUOTE,
)
ENGAGEMENT_CLAIM = chain_claim(
    "target_engagement",
    "Divarasib occupies KRAS G12C in the tumours of patients.",
    ENGAGEMENT_QUOTE,
)


def filled(conn, *new_claims: dict, run_id: str = "R-2"):
    answer = {"links": [], "new_claims": list(new_claims)}
    bundle = prepare_recompute(conn, "R-1", run_id, [PK_DOC], EARLY)
    llm = FakeLLM(
        {
            "reasoning.classify": answer,
            "chair": {"questions": []},
            "synthesis": {"theses": []},
            "judge": {"judgments": []},
        }
    )
    return finish_recompute(conn, run_id, lambda: bundle, lambda: llm)


def test_a_document_on_human_exposure_moves_that_link_from_missing_to_weak(conn) -> None:
    gap = next(c for c in load_claims(conn, "R-1")[0] if c.chain_link is ChainLink.HUMAN_EXPOSURE)

    assert filled(conn, EXPOSURE_CLAIM) is not None and get_run(conn, "R-2").status == DONE

    diff = build_diff(conn, "R-1", "R-2")
    (moved,) = [c for c in diff.chain if c.link is ChainLink.HUMAN_EXPOSURE]
    assert moved.status_before == "missing" and moved.status_after in ("weak", "supported")
    assert (moved.confidence_before or 0) < 0.4 <= (moved.confidence_after or 0)
    assert [c.link for c in diff.chain] == [ChainLink.HUMAN_EXPOSURE]  # no other link moved
    # The gap is gone, the claim that closes it is new, and the diff says which evidence did it.
    removed = [c for c in diff.claims if c.change == "removed"]
    added = [c for c in diff.claims if c.change == "added"]
    assert [c.text for c in removed] == [gap.text]
    assert [(c.text, c.new_evidence_ids) for c in added] == [(EXPOSURE_CLAIM["text"], [NEW_ID])]


def test_the_diff_names_the_claims_and_quotes_that_changed_the_translation_answer(conn) -> None:
    filled(conn, EXPOSURE_CLAIM, ENGAGEMENT_CLAIM)

    modules = {m.module.value: m for m in build_diff(conn, "R-1", "R-2").modules}
    translation = next(m for name, m in modules.items() if name.startswith("preclinical"))

    # Soft gate S1 held the module at Mixed while two links were missing; with both filled it
    # no longer fires and the answer changes. The balance was already at its ceiling.
    assert translation.changed and translation.answer_before != translation.answer_after
    assert translation.answer_before.value == "mixed"
    causes = {c.quote: c for c in translation.causes}
    assert set(causes) == {EXPOSURE_QUOTE, ENGAGEMENT_QUOTE}
    cause = causes[EXPOSURE_QUOTE]
    assert (cause.evidence_id, cause.claim_change) == (NEW_ID, "added")
    assert cause.claim_text == EXPOSURE_CLAIM["text"] and cause.direction.value == "supports"
    assert cause.url == PK_DOC.url


def test_the_confidence_of_the_new_chain_claim_comes_from_the_formula(conn) -> None:
    filled(conn, EXPOSURE_CLAIM)

    claims, links = load_claims(conn, "R-2")
    (claim,) = [c for c in claims if c.text == EXPOSURE_CLAIM["text"]]
    assert claim.id.startswith("C-") and claim.chain_link is ChainLink.HUMAN_EXPOSURE
    assert claim.confidence_parts is not None and claim.confidence_parts.support > 0
    assert 0.4 <= claim.confidence < 1.0
    assert not [c for c in claims if c.basis is Basis.UNKNOWN and c.chain_link is claim.chain_link]
    assert all(l.claim_id in {c.id for c in claims} for l in links)  # no link left on the gap


def test_the_last_missing_link_filled_clears_gate_s1(conn) -> None:
    filled(conn, EXPOSURE_CLAIM)
    s1 = {g.gate_id: g for g in build_diff(conn, "R-1", "R-2").gates}
    assert GateId.S1 not in s1  # target engagement is still missing: the gate still fires

    filled(conn, EXPOSURE_CLAIM, ENGAGEMENT_CLAIM, run_id="R-3")

    diff = build_diff(conn, "R-1", "R-3")
    (gate,) = [g for g in diff.gates if g.gate_id is GateId.S1]
    assert gate.fired_before and not gate.fired_after
    assert {c.link for c in diff.chain} == {ChainLink.HUMAN_EXPOSURE, ChainLink.TARGET_ENGAGEMENT}


def test_a_closed_gap_is_logged_on_the_run(conn) -> None:
    filled(conn, EXPOSURE_CLAIM)

    detail = " ".join(e.detail or "" for e in load_events(conn, "R-2"))
    assert "1 chain-link gap(s) closed" in detail
    (check,) = [c for c in load_checks(conn, "R-2") if c.check_name == "gap_closed"]
    assert check.passed and "replaces C-" in check.detail
