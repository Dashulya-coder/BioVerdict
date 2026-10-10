"""Adding a document must move exactly the claims it touches, and only by what the formula says."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.llm import FakeLLM
from bioverdict.reasoning import ModuleReasoner
from bioverdict.reasoning.classify_evidence import (
    STEP,
    Classification,
    NewLink,
    build_prompt,
    build_prompts,
    classify_new_evidence,
)
from bioverdict.reasoning.grounding import DropKind
from bioverdict.reasoning.schemas import DraftClaim, DraftLink
from bioverdict.scoring.verdict import rescore
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    ClaimType,
    DiligenceType,
    Direction,
    Evidence,
    EvidenceLevel,
    GateId,
    Implication,
    Section,
    SourceKind,
    Verdict,
)

ROOT = Path(__file__).parents[3]
BUNDLE = Bundle.model_validate_json((ROOT / "fixtures/bundles/divarasib.json").read_text())
DRAFTS = json.loads((ROOT / "fixtures/reasoning/divarasib.json").read_text())
AS_OF = date(2026, 10, 7)


def finished_run():
    """The claims, links and verdict of the fixture run: the report that is already written."""
    claims, links = ModuleReasoner(FakeLLM(DRAFTS), "R-1").reason(BUNDLE)
    _, result = rescore(claims, links, BUNDLE.evidence_by_id(), AS_OF)
    return claims, links, result


def added(eid: str, text: str, level: EvidenceLevel, group: str, kind=SourceKind.PEER_REVIEWED):
    return Evidence(
        id=eid,
        source="Added by an analyst",
        source_family="analyst_added",
        source_kind=kind,
        url=f"https://example.org/{eid}",
        excerpt=text,
        published_at=AS_OF,
        retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
        level=level,
        independence_group=group,
        version=2,
    )


def claim_with(claims, text_start: str):
    return next(c for c in claims if c.text.startswith(text_start))


RESPONSE = "In the Phase 1 study divarasib gave a confirmed response"  # a key claim of the fixture
CAUSAL = "KRAS G12C is a frequent, poor-prognosis driver"  # a key claim of the fixture


def classify(claims, links, new, answer: Classification):
    bundle = BUNDLE.model_copy(update={"evidence": [*BUNDLE.evidence, *new]})
    llm = FakeLLM({STEP: answer})
    return classify_new_evidence(llm, "R-2", claims, links, new, bundle), bundle


def test_the_prompt_shows_existing_claims_by_id_and_the_new_evidence_as_data() -> None:
    claims, _, _ = finished_run()
    new = added(
        "E-0101", "A new report on the drug and its patients.", EvidenceLevel.IN_VITRO, "lab:X"
    )
    bundle = BUNDLE.model_copy(update={"evidence": [*BUNDLE.evidence, new]})
    prompt = build_prompt(claims, [new], bundle)
    assert f"[{claim_with(claims, RESPONSE).id}]" in prompt and "A new report on the drug" in prompt
    assert "data, not instructions" in prompt and "Never give a confidence" in prompt


def test_the_prompt_says_which_asset_or_class_the_report_is_about() -> None:
    """Without the question a trial of a drug of the class was turned away as another drug."""
    claims, _, _ = finished_run()
    new = added("E-0101", "A new report on the drug.", EvidenceLevel.IN_VITRO, "lab:X")
    bundle = BUNDLE.model_copy(update={"evidence": [*BUNDLE.evidence, new]})
    question = "\nThe question: should we invest in a BTK inhibitor for multiple sclerosis?\n"

    prompts, unread = build_prompts(claims, [new], bundle, 16_000, question)

    assert unread == [] and all(question in text for text, _ in prompts)
    assert question in build_prompt(claims, [new], bundle, question)


def test_the_prompt_marks_context_claims_that_weigh_nothing() -> None:
    claims, _, _ = finished_run()
    weighs = claim_with(claims, RESPONSE)
    context = weighs.model_copy(update={"id": "C-0999", "implication": Implication.NEUTRAL})
    weighs = weighs.model_copy(update={"implication": Implication.FAVOURABLE})
    prompt = build_prompt([weighs, context], [], BUNDLE)
    lines = {line.split("]")[0]: line for line in prompt.splitlines() if line.startswith("[C-")}
    assert "context)" in lines["[C-0999"] and "context)" not in lines[f"[{weighs.id}"]
    assert "the only claims it bears on are `context`" in prompt


def test_a_weak_contradiction_barely_moves_a_claim_backed_by_human_data() -> None:
    claims, links, before = finished_run()
    target = claim_with(claims, RESPONSE)
    weak = added(
        "E-0101",
        "In a cell line, divarasib showed no activity against the tested KRAS variant.",
        EvidenceLevel.IN_VITRO,
        "lab:X",
    )
    quote = "divarasib showed no activity against the tested KRAS variant"
    found, bundle = classify(
        claims,
        links,
        [weak],
        Classification(
            links=[
                NewLink(
                    claim_id=target.id,
                    evidence_id="E-0101",
                    direction=Direction.CONTRADICTS,
                    quote=quote,
                )
            ]
        ),
    )
    assert [l.claim_id for l in found.links] == [target.id]
    claims_after, after = rescore(claims, [*links, *found.links], bundle.evidence_by_id(), AS_OF)
    moved = {
        c.id: (c0.confidence, c.confidence) for c0, c in zip(claims, claims_after, strict=True)
    }
    old, new = moved[target.id]
    assert old - new < 0.05  # in vitro against a phase 1 result: barely moves
    assert {i for i, (o, n) in moved.items() if o != n} == {target.id}  # and nothing else does
    assert after.verdict is before.verdict


def test_a_strong_contradiction_lowers_the_claim_clearly_and_touches_nothing_else() -> None:
    claims, links, _ = finished_run()
    target = claim_with(claims, RESPONSE)
    strong = added(
        "E-0102",
        "In the randomized trial divarasib did not improve progression-free survival over sotorasib.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "trial:NCT0000001",
    )
    quote = "divarasib did not improve progression-free survival over sotorasib"
    found, bundle = classify(
        claims,
        links,
        [strong],
        Classification(
            links=[
                NewLink(
                    claim_id=target.id,
                    evidence_id="E-0102",
                    direction=Direction.CONTRADICTS,
                    quote=quote,
                )
            ]
        ),
    )
    claims_after, _ = rescore(claims, [*links, *found.links], bundle.evidence_by_id(), AS_OF)
    moved = {
        c.id: (c0.confidence, c.confidence) for c0, c in zip(claims, claims_after, strict=True)
    }
    old, new = moved[target.id]
    assert old - new > 0.15  # a human result against it: a clear drop
    assert {i for i, (o, n) in moved.items() if o != n} == {target.id}


def test_a_new_safety_fact_from_two_independent_sources_flips_the_verdict() -> None:
    claims, links, before = finished_run()
    assert before.verdict is Verdict.CONDITIONAL
    first = added(
        "E-0103",
        "FDA placed a clinical hold on divarasib trials after two treatment-related deaths.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "regulator:FDA",
        SourceKind.REGULATOR,
    )
    second = added(
        "E-0104",
        "The company disclosed the clinical hold and the two treatment-related deaths.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "company:Roche",
        SourceKind.COMPANY,
    )
    fact = DraftClaim(
        text="FDA placed divarasib on clinical hold after two treatment-related deaths",
        claim_type=ClaimType.STUDY_FACT,
        basis="extracted",
        gate_signals=[GateId.K2],
        links=[
            {
                "evidence_id": "E-0103",
                "direction": "supports",
                "quote": "FDA placed a clinical hold on divarasib trials",
            },
            {
                "evidence_id": "E-0104",
                "direction": "supports",
                "quote": "disclosed the clinical hold and the two",
            },
        ],
    )
    found, bundle = classify(claims, links, [first, second], Classification(new_claims=[fact]))
    assert len(found.new_claims) == 1 and found.new_claims[0].gate_signals == [GateId.K2]
    all_claims = [*claims, *found.new_claims]
    _, after = rescore(all_claims, [*links, *found.new_claim_links], bundle.evidence_by_id(), AS_OF)
    assert next(g for g in after.gates if g.gate_id is GateId.K2).fired
    assert after.verdict is Verdict.DO_NOT_INVEST


def test_the_same_safety_fact_from_one_source_only_caps_the_verdict() -> None:
    claims, links, _ = finished_run()
    only = added(
        "E-0103",
        "FDA placed a clinical hold on divarasib trials after two treatment-related deaths.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "regulator:FDA",
        SourceKind.REGULATOR,
    )
    fact = DraftClaim(
        text="FDA placed divarasib on clinical hold",
        claim_type=ClaimType.STUDY_FACT,
        basis="extracted",
        gate_signals=[GateId.K2],
        links=[
            {
                "evidence_id": "E-0103",
                "direction": "supports",
                "quote": "FDA placed a clinical hold on divarasib trials",
            }
        ],
    )
    found, bundle = classify(claims, links, [only], Classification(new_claims=[fact]))
    _, after = rescore(
        [*claims, *found.new_claims],
        [*links, *found.new_claim_links],
        bundle.evidence_by_id(),
        AS_OF,
    )
    assert not next(g for g in after.gates if g.gate_id is GateId.K2).fired
    assert after.verdict is not Verdict.DO_NOT_INVEST  # one source: confirm it first


def test_an_invented_link_or_quote_is_dropped_not_trusted() -> None:
    claims, links, _ = finished_run()
    target = claim_with(claims, RESPONSE)
    new = added(
        "E-0105", "A short note without findings about the program.", EvidenceLevel.IN_VITRO, "g"
    )
    bad = Classification(
        links=[
            NewLink(
                claim_id="C-9999",
                evidence_id="E-0105",
                direction=Direction.SUPPORTS,
                quote="A short note without findings",
            ),
            NewLink(
                claim_id=target.id,
                evidence_id="E-0001",
                direction=Direction.SUPPORTS,
                quote="assess the safety and efficacy",
            ),
            NewLink(
                claim_id=target.id,
                evidence_id="E-0105",
                direction=Direction.CONTRADICTS,
                quote="the drug was shown to fail",
            ),
            NewLink(
                claim_id=target.id, evidence_id="E-0105", direction=Direction.CONTRADICTS, quote="x"
            ),
        ],
        unmatched=["E-0105", "E-7777"],
    )
    found, _ = classify(claims, links, [new], bad)
    assert found.links == []
    reasons = [d.reason for d in found.drops]
    assert "no such claim" in reasons and "not a piece of the new evidence" in reasons
    assert "quote is not in the excerpt" in reasons and any("shorter than" in r for r in reasons)
    assert found.unmatched == ["E-0105"]  # an id that is not new evidence is ignored


def test_a_link_that_already_exists_is_not_added_twice() -> None:
    claims, links, _ = finished_run()
    old = links[0]
    again = Classification(
        links=[
            NewLink(
                claim_id=old.claim_id,
                evidence_id=old.evidence_id,
                direction=old.direction,
                quote=old.quote,
            )
        ]
    )
    new = BUNDLE.evidence_by_id()[old.evidence_id]  # counted as new here, for the test
    found, _ = classify(claims, links, [new], again)
    assert found.links == [] and any(d.kind is DropKind.DUPLICATE_LINK for d in found.drops)


def test_new_claims_are_numbered_after_the_existing_ones_and_never_assert_a_gap_as_a_gate() -> None:
    claims, links, _ = finished_run()
    last = max(int(c.id.removeprefix("C-")) for c in claims)
    new = added(
        "E-0106",
        "Development of the asset was discontinued by the sponsor.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "company:X",
        SourceKind.COMPANY,
    )
    unknown = DraftClaim(
        text="We do not know whether the program continues",
        claim_type=ClaimType.STUDY_FACT,
        basis="unknown",
        diligence_type="proprietary_data",
        gate_signals=[GateId.K4],
        links=[
            {
                "evidence_id": "E-0106",
                "direction": "supports",
                "quote": "Development of the asset was discontinued",
            }
        ],
    )
    found, _ = classify(claims, links, [new], Classification(new_claims=[unknown]))
    assert [c.id for c in found.new_claims] == [f"C-{last + 1:04d}"]
    assert found.new_claims[0].basis is Basis.UNKNOWN and found.new_claims[0].gate_signals == []


def test_a_new_fact_about_the_target_is_a_mechanism_claim_and_the_numbering_follows() -> None:
    claims, links, _ = finished_run()
    last = max(int(c.id.removeprefix("C-")) for c in claims)
    lab = added(
        "E-0101",
        "Inhibition of the target prevented myelin loss in the co-culture.",
        EvidenceLevel.IN_VITRO,
        "lab:X",
        SourceKind.PREPRINT,
    )
    stop = added(
        "E-0102",
        "Development of the asset was discontinued by the sponsor.",
        EvidenceLevel.HUMAN_INTERVENTIONAL,
        "company:X",
        SourceKind.COMPANY,
    )

    def draft(text, claim_type, evidence, quote):
        return DraftClaim(
            text=text,
            claim_type=claim_type,
            basis="extracted",
            implication=Implication.FAVOURABLE,
            links=[{"evidence_id": evidence.id, "direction": "supports", "quote": quote}],
        )

    found, _ = classify(
        claims,
        links,
        [lab, stop],
        Classification(
            new_claims=[
                draft("The sponsor stopped the asset", ClaimType.STUDY_FACT, stop, stop.excerpt),
                draft(
                    "Inhibiting the target prevented myelin loss in the laboratory",
                    ClaimType.TARGET_CAUSAL,
                    lab,
                    "Inhibition of the target prevented myelin loss",
                ),
            ]
        ),
    )

    by_type = {c.claim_type: c for c in found.new_claims}
    assert by_type[ClaimType.TARGET_CAUSAL].section is Section.MECHANISM
    assert by_type[ClaimType.STUDY_FACT].section is Section.CLINICAL
    assert sorted(c.id for c in found.new_claims) == [f"C-{last + 1:04d}", f"C-{last + 2:04d}"]


@pytest.mark.parametrize("valid_link", [False, True])
def test_one_invented_citation_drops_the_whole_new_claim(valid_link) -> None:
    claims, links, before = finished_run()
    new = added(
        "E-0101", "The study reports a safety finding.", EvidenceLevel.HUMAN_INTERVENTIONAL, "g"
    )
    citations = [{"evidence_id": new.id, "direction": "supports", "quote": "invented finding"}]
    if valid_link:
        citations.insert(0, {"evidence_id": new.id, "direction": "supports", "quote": new.excerpt})
    draft = DraftClaim(
        text="An unsupported safety conclusion",
        claim_type=ClaimType.OTHER,
        basis="extracted",
        links=citations,
    )
    found, bundle = classify(claims, links, [new], Classification(new_claims=[draft]))
    assert found.new_claims == [] and found.new_claim_links == []
    assert len(found.rejected_claims) == 1
    _, after = rescore(claims, links, bundle.evidence_by_id(), AS_OF)
    assert after == before


def test_an_inference_without_any_citation_is_not_added() -> None:
    claims, links, _ = finished_run()
    new = added("E-0101", "A note about the study.", EvidenceLevel.IN_VITRO, "g")
    found, _ = classify(
        claims,
        links,
        [new],
        Classification(
            new_claims=[
                DraftClaim(
                    text="A conclusion from model memory",
                    claim_type=ClaimType.OTHER,
                    basis="inferred",
                )
            ]
        ),
    )
    assert found.new_claims == [] and len(found.rejected_claims) == 1


def test_a_report_of_dozens_of_claims_still_leaves_room_for_the_new_evidence() -> None:
    from bioverdict.llm.sizing import wire_len
    from bioverdict.reasoning.classify_evidence import build_prompts
    from bioverdict.reasoning.prompts import RETRY_RESERVE

    claims, _, _ = finished_run()
    many = [
        claims[0].model_copy(
            update={"id": f"C-{n:04d}", "text": "a long claim about the drug " * 12}
        )
        for n in range(1, 71)
    ]
    document = added(
        "E-9001", "A decisive result, stated plainly.", EvidenceLevel.HUMAN_INTERVENTIONAL, "g"
    )
    budget = 16_000

    prompts, unread = build_prompts(many, [document], BUNDLE, budget)

    assert unread == [] and len(prompts) == 1
    text, shown = prompts[0]
    assert shown == [document] and "A decisive result, stated plainly." in text
    assert wire_len(text) + RETRY_RESERVE <= budget
    assert "[C-0070]" in text  # every claim can still be linked


def test_evidence_about_another_drug_or_disease_is_to_be_left_unmatched() -> None:
    prompt = build_prompt([], [], BUNDLE)

    assert "another drug" in prompt and "unmatched" in prompt


# --- a new fact on a link of the translation chain can close that link's gap -------------------------

EXPOSURE = (
    "Plasma exposure of divarasib at the recommended dose exceeded the concentration that "
    "inhibited KRAS G12C signalling in the cell models."
)


def exposure_claim(**changes) -> DraftClaim:
    draft = DraftClaim(
        text="Divarasib reaches an exposure in patients above the effective experimental one.",
        claim_type=ClaimType.DRUG_ACTS_IN_HUMANS,
        basis="extracted",
        chain_link=ChainLink.HUMAN_EXPOSURE,
        links=[DraftLink(evidence_id="E-0101", direction=Direction.SUPPORTS, quote=EXPOSURE)],
    )
    return draft.model_copy(update=changes)


def exposure_run(draft: DraftClaim):
    claims, links, _ = finished_run()
    gap = next(c for c in claims if c.chain_link is ChainLink.HUMAN_EXPOSURE)
    assert gap.basis is Basis.UNKNOWN  # the fixture's report says the link is not shown
    new = added("E-0101", EXPOSURE, EvidenceLevel.HUMAN_INTERVENTIONAL, "pk:X")
    result, _ = classify(claims, links, [new], Classification(new_claims=[draft]))
    return gap, result


def test_a_fact_that_shows_a_chain_link_is_a_translation_claim_and_closes_the_gap() -> None:
    gap, result = exposure_run(exposure_claim())

    (claim,) = result.new_claims
    assert (claim.section, claim.chain_link) == (Section.TRANSLATION, ChainLink.HUMAN_EXPOSURE)
    assert claim.claim_type is ClaimType.DRUG_ACTS_IN_HUMANS and claim.confidence == 0.0
    assert [(l.claim_id, l.evidence_id) for l in result.new_claim_links] == [(claim.id, "E-0101")]
    assert result.gaps_closed == {gap.id: claim.id}
    assert not [d for d in result.drops if d.kind is DropKind.CHAIN_LINK]


def test_the_claim_type_of_a_chain_claim_is_set_by_code_not_by_the_model() -> None:
    _, result = exposure_run(exposure_claim(claim_type=ClaimType.TARGET_CAUSAL))

    assert result.new_claims[0].claim_type is ClaimType.DRUG_ACTS_IN_HUMANS


def test_a_new_gap_closes_nothing() -> None:
    gap, result = exposure_run(
        exposure_claim(basis="unknown", links=[], diligence_type=DiligenceType.PATIENT_LEVEL_DATA)
    )

    assert result.new_claims and result.gaps_closed == {}
    assert gap.id not in result.gaps_closed


def test_a_chain_claim_with_an_invented_quote_is_rejected_and_closes_nothing() -> None:
    link = DraftLink(evidence_id="E-0101", direction=Direction.SUPPORTS, quote="Never written.")
    _, result = exposure_run(exposure_claim(links=[link]))

    assert result.new_claims == [] and result.gaps_closed == {}
    assert result.rejected_claims


def test_a_claim_that_asserts_a_gate_stays_clinical_and_loses_the_chain_link() -> None:
    _, result = exposure_run(exposure_claim(gate_signals=[GateId.K2]))

    (claim,) = result.new_claims
    assert claim.section is Section.CLINICAL and claim.chain_link is None
    assert [d for d in result.drops if d.kind is DropKind.CHAIN_LINK]
    assert result.gaps_closed == {}


def test_the_prompt_names_the_chain_link_of_a_claim() -> None:
    claims, _, _ = finished_run()
    gap = next(c for c in claims if c.chain_link is ChainLink.HUMAN_EXPOSURE)

    prompt = build_prompt(
        claims, [added("E-0101", EXPOSURE, EvidenceLevel.IN_VITRO, "pk:X")], BUNDLE
    )

    assert f"[{gap.id}] (translation, unknown, human_exposure, context)" in prompt


def test_on_the_gateway_a_report_of_hundreds_of_claims_leaves_room_for_the_new_evidence() -> None:
    """At 16,000 characters a run of 88 claims left no room and the documents went unread."""
    from bioverdict.llm import LLMClient, LLMConfig
    from bioverdict.llm.providers.fake import FakeProvider
    from bioverdict.llm.providers.openai import OpenAIProvider
    from bioverdict.reasoning.classify_evidence import STEP, Classification, build_prompts

    class GatewayLike(FakeProvider):
        input_chars = OpenAIProvider(client=object()).input_chars

    llm = LLMClient(LLMConfig.for_provider("openai"), {"openai": GatewayLike("{}", name="openai")})
    claims, _, _ = finished_run()
    many = [
        claims[0].model_copy(update={"id": f"C-{n:04d}", "text": "a claim about a trial " * 8})
        for n in range(1, 300)
    ]
    new = [
        added(f"E-900{n}", f"Decisive result {n}.", EvidenceLevel.HUMAN_INTERVENTIONAL, f"g{n}")
        for n in (1, 2)
    ]

    prompts, unread = build_prompts(many, new, BUNDLE, llm.input_budget(STEP, Classification))

    assert unread == [] and len(prompts) == 1
    assert "Decisive result 1." in prompts[0][0] and "[C-0299]" in prompts[0][0]
