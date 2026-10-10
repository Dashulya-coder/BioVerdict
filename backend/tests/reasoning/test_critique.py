"""The Skeptic and the Chair propose; code keeps only what it can check and ranks by the verdict."""

from pathlib import Path

import pytest

from bioverdict.llm import FakeLLM
from bioverdict.llm.errors import FatalProviderError
from bioverdict.pipeline.reason_score import chair_pass, skeptic_pass
from bioverdict.reasoning.critique import ask, chair_prompt, challenge, skeptic_prompt
from bioverdict.scoring.confidence import apply_confidence
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    DiligenceType,
    Direction,
    Section,
)
from bioverdict.store.runs_repo import create_run, load_events

BUNDLE = Bundle.model_validate_json(
    (Path(__file__).parents[3] / "fixtures/bundles/divarasib.json").read_text()
)
QUOTE = "Treatment-related adverse events occurred in 127 patients (93%)"


def claim(cid: str, confidence: float = 0.8, **kw) -> Claim:
    base = {
        "id": cid,
        "run_id": "R-1",
        "section": Section.CLINICAL,
        "text": f"claim {cid}",
        "claim_type": ClaimType.OTHER,
        "basis": Basis.EXTRACTED,
        "confidence": confidence,
    }
    return Claim(**(base | kw))


def objection(**kw) -> dict:
    return {
        "claim_id": "C-1",
        "evidence_id": "E-0008",
        "quote": QUOTE,
        "objection": "nearly everyone had an adverse event",
    } | kw


def skeptic(*items: dict) -> FakeLLM:
    return FakeLLM({"skeptic": {"objections": list(items)}})


def test_a_grounded_objection_becomes_a_contradicting_link() -> None:
    found = challenge(skeptic(objection()), BUNDLE, [claim("C-1")], [])

    assert [(l.claim_id, l.evidence_id, l.direction) for l in found.links] == [
        ("C-1", "E-0008", Direction.CONTRADICTS)
    ]
    assert found.objections == ["C-1: nearly everyone had an adverse event"]
    assert [(c.check_name, c.passed) for c in found.checks] == [("skeptic_objection", True)]


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"quote": "a sentence the document never says"}, "quote is not in the excerpt"),
        ({"evidence_id": "E-9999"}, "evidence is not in the bundle"),
        ({"claim_id": "C-77"}, "claim is not in the report"),
        ({"quote": "93%"}, "shorter than"),
    ],
)
def test_an_objection_code_cannot_ground_is_dropped_and_logged(change: dict, why: str) -> None:
    found = challenge(skeptic(objection(**change)), BUNDLE, [claim("C-1")], [])

    assert found.links == [] and found.objections == []
    assert [(c.check_name, c.passed) for c in found.checks] == [("skeptic_ungrounded", False)]
    assert why in found.checks[0].detail


def test_evidence_a_claim_already_cites_is_not_an_objection_against_it() -> None:
    cited = ClaimEvidenceLink(
        claim_id="C-1", evidence_id="E-0008", direction=Direction.SUPPORTS, quote=QUOTE
    )

    found = challenge(skeptic(objection()), BUNDLE, [claim("C-1")], [cited])

    assert found.links == []
    assert "already cites" in found.checks[0].detail


def test_the_skeptic_sees_the_claims_and_the_evidence() -> None:
    prompt = skeptic_prompt(BUNDLE, [claim("C-1", critical=True)], budget=None)

    assert "C-1 [extracted; confidence 0.80; clinical; critical]: claim C-1" in prompt
    assert 'id="E-0008"' in prompt


def chair(*items: dict) -> FakeLLM:
    return FakeLLM({"chair": {"questions": list(items)}})


def question(claim_id: str, text: str = "Who knows?", **kw) -> dict:
    return {"text": text, "claim_id": claim_id, "answered_by": "kol_interview"} | kw


def gap(cid: str, link: ChainLink, **kw) -> Claim:
    return claim(
        cid,
        0.1,
        basis=Basis.UNKNOWN,
        section=Section.TRANSLATION,
        chain_link=link,
        diligence_type=DiligenceType.EXPERIMENT,
        **kw,
    )


def chain_without(link: ChainLink) -> list[Claim]:
    return [
        claim(f"L-{l.value}", 0.9, chain_link=l, section=Section.TRANSLATION)
        for l in ChainLink
        if l is not link
    ]


def test_questions_are_ranked_by_what_the_answer_would_do_to_the_verdict() -> None:
    claims = [
        *chain_without(ChainLink.TARGET_ENGAGEMENT),
        gap("C-gap", ChainLink.TARGET_ENGAGEMENT),
        claim("K", 0.9, critical=True),
        claim("C-side", 0.9),
    ]
    llm = chair(question("C-side", "Is the side claim right?"), question("C-gap", "Is it engaged?"))

    ranked = ask(llm, BUNDLE, claims, [], [])

    assert [q.text for q in ranked] == ["Is it engaged?", "Is the side claim right?"]
    assert ranked[0].value_of_information > ranked[1].value_of_information == 0
    assert ranked[0].answered_by is DiligenceType.KOL_INTERVIEW


def test_a_question_about_a_claim_that_is_not_in_the_report_is_dropped() -> None:
    assert ask(chair(question("C-77")), BUNDLE, [claim("C-1")], [], []) == []


def test_an_unknown_claim_the_chair_skipped_still_becomes_a_question() -> None:
    claims = [claim("C-1"), gap("C-gap", ChainLink.HUMAN_EXPOSURE)]

    ranked = ask(chair(), BUNDLE, claims, [], [])

    assert [q.text for q in ranked] == ["Can this be established? claim C-gap"]
    assert ranked[0].answered_by is DiligenceType.EXPERIMENT


def test_a_repeated_question_and_a_third_one_about_a_claim_are_dropped() -> None:
    claims = [claim("C-1")]
    llm = chair(
        question("C-1", "A?"),
        question("C-1", " a? "),
        question("C-1", "B?"),
        question("C-1", "C?"),
    )

    assert [q.text for q in ask(llm, BUNDLE, claims, [], [])] == ["A?", "B?"]


def test_the_chair_is_told_about_near_misses_and_objections() -> None:
    prompt = chair_prompt(BUNDLE, [claim("C-1")], ["S4 would fire if..."], ["C-1: weak"])

    assert "S4 would fire if..." in prompt and "C-1: weak" in prompt
    assert "Evidence" not in prompt  # the Chair reads claims, not documents


@pytest.fixture
def conn():
    connection = connect(":memory:")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, BUNDLE.as_of)
    yield connection
    connection.close()


class Broken:
    def call(self, step, prompt, schema):
        raise FatalProviderError("gateway down")


def test_a_failed_skeptic_leaves_the_claims_alone_and_the_run_says_so(conn) -> None:
    claims = [claim("C-1")]

    out, links, objections = skeptic_pass(conn, "R-1", BUNDLE, Broken(), claims, [])

    assert out == claims and links == [] and objections == []
    assert [(e.step, e.status) for e in load_events(conn, "R-1")] == [
        ("skeptic", "started"),
        ("skeptic", "skipped"),
    ]


def test_a_failed_chair_gives_no_questions_and_the_run_says_so(conn) -> None:
    claims = [claim("C-1")]

    assert chair_pass(conn, "R-1", BUNDLE, Broken(), claims, score_verdict(claims), []) == []
    assert load_events(conn, "R-1")[-1].status == "skipped"


def test_an_objection_lowers_the_claim_it_contradicts_by_the_formula(conn) -> None:
    quote = "a confirmed response was observed in 53.4% of patients"
    supports = ClaimEvidenceLink(
        claim_id="C-1", evidence_id="E-0007", direction=Direction.SUPPORTS, quote=quote
    )
    before = apply_confidence([claim("C-1")], [supports], BUNDLE.evidence_by_id(), BUNDLE.as_of)

    out, links, objections = skeptic_pass(
        conn, "R-1", BUNDLE, skeptic(objection()), before, [supports]
    )

    assert len(links) == 2 and objections
    assert out[0].confidence < before[0].confidence


def test_a_long_list_of_notes_cannot_crowd_the_claims_out_of_the_chairs_request() -> None:
    from bioverdict.llm.sizing import wire_len
    from bioverdict.reasoning.prompts import RETRY_RESERVE

    budget = 16_000
    claims = [
        claim(f"C-{n:04d}", 0.8, text="a fairly long claim about the drug " * 6)
        for n in range(1, 81)
    ]
    claims.append(claim("C-9999", 0.9, critical=True, text="the key claim"))

    chair = chair_prompt(BUNDLE, claims, ["near miss " * 60] * 40, ["objection " * 60] * 40, budget)

    assert wire_len(chair) + RETRY_RESERVE <= budget
    assert chair.count("- near miss") == 8 and chair.count("- objection") == 8
    assert "C-9999" in chair
