from pathlib import Path

import pytest

from bioverdict.contracts import Reasoner
from bioverdict.llm import FakeLLM
from bioverdict.reasoning import MECHANISM, TRANSLATION, ModuleReasoner
from bioverdict.reasoning.grounding import ground_draft
from bioverdict.reasoning.prompts import build_prompt
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    DiligenceType,
    Direction,
    GateId,
    Section,
    SectionStatus,
    Verdict,
)

FIXTURE = Path(__file__).parents[3] / "fixtures" / "bundles" / "divarasib.json"
BUNDLE = Bundle.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

ORR = "a confirmed response was observed in 53.4% of patients"  # in E-0007
G12C = "found in approximately 14% of NSCLC cases"  # in E-0006
STRUCTURE = "takes on a distinct conformation"  # in E-0010 (in vitro)
CT_SUMMARY = "assess the safety and efficacy of divarasib"  # in E-0001


def link(evidence_id: str, quote: str, direction: str = "supports") -> dict:
    return {"evidence_id": evidence_id, "direction": direction, "quote": quote}


def claim(text: str, **kw) -> dict:
    base = {"text": text, "claim_type": "other", "basis": "extracted", "links": []}
    return base | kw


def draft(*claims: dict) -> ModuleDraft:
    return ModuleDraft.model_validate({"claims": list(claims)})


def ground(d: ModuleDraft, module=MECHANISM, **kw):
    return ground_draft(
        d,
        BUNDLE,
        "R-1",
        module.section,
        allowed_gates=module.allowed_gates,
        allow_chain=module.chain,
        **kw,
    )


# --- grounding --------------------------------------------------------------


def test_grounded_claim_keeps_its_links() -> None:
    g = ground(draft(claim("G12C is common", links=[link("E-0006", G12C)])))
    assert [c.basis for c in g.claims] == [Basis.EXTRACTED]
    assert [(l.evidence_id, l.direction) for l in g.links] == [("E-0006", Direction.SUPPORTS)]
    assert g.claims[0].id == "C-0001" and not g.drops


def test_quote_not_in_the_text_is_dropped_and_claim_is_downgraded() -> None:
    g = ground(draft(claim("It works", links=[link("E-0007", "response rate was 99%")])))
    assert not g.links
    assert g.claims[0].basis is Basis.INFERRED  # no grounded quote left
    assert {d.reason for d in g.drops} >= {"quote is not in the excerpt"}


def test_evidence_that_is_not_in_the_bundle_is_dropped() -> None:
    g = ground(draft(claim("x", links=[link("E-9999", "anything")])))
    assert not g.links and g.drops[0].reason == "evidence is not in the bundle"


def test_the_same_evidence_cited_twice_counts_once() -> None:
    g = ground(draft(claim("x", links=[link("E-0006", G12C), link("E-0006", "poor prognosis")])))
    assert len(g.links) == 1


def test_a_claim_stays_extracted_while_at_least_one_quote_survives() -> None:
    g = ground(draft(claim("x", links=[link("E-0006", G12C), link("E-0007", "invented")])))
    assert g.claims[0].basis is Basis.EXTRACTED and len(g.links) == 1  # one quote survived


def test_unknown_claim_gets_a_diligence_type_and_a_status() -> None:
    g = ground(draft(claim("Nobody has shown this", basis="unknown")))
    c = g.claims[0]
    assert c.basis is Basis.UNKNOWN and c.diligence_type is DiligenceType.PROPRIETARY_DATA
    assert c.status is SectionStatus.NONE_FOUND  # the mechanism section was searched


def test_unknown_in_an_unsearched_section_is_not_searched() -> None:
    bundle = BUNDLE.model_copy(update={"section_statuses": {}})
    g = ground_draft(
        draft(claim("?", basis="unknown")),
        bundle,
        "R",
        Section.MECHANISM,
    )
    assert g.claims[0].status is SectionStatus.NOT_SEARCHED


def test_gate_outside_the_modules_remit_is_removed() -> None:
    g = ground(draft(claim("x", gate_signals=["K3", "K1"])), MECHANISM)
    assert g.claims[0].gate_signals == [GateId.K3]
    assert any(d.what == "K1" for d in g.drops)
    assert ground(draft(claim("x", gate_signals=["K3"])), TRANSLATION).claims[0].gate_signals == []


def test_chain_link_is_kept_only_in_the_translation_module() -> None:
    d = draft(claim("x", chain_link="human_exposure"))
    assert ground(d, MECHANISM).claims[0].chain_link is None
    assert ground(d, TRANSLATION).claims[0].chain_link is ChainLink.HUMAN_EXPOSURE


def test_empty_claims_are_dropped_and_ids_continue() -> None:
    g = ground(draft(claim("  "), claim("real")), first_number=5)
    assert [c.id for c in g.claims] == ["C-0005"] and g.drops[0].reason == "empty text"


# --- prompt -----------------------------------------------------------------


def test_prompt_lists_all_evidence_verbatim_and_states_the_closed_world() -> None:
    prompt = build_prompt(MECHANISM.instruction, BUNDLE)
    for item in BUNDLE.evidence:
        assert f"[{item.id}]" in prompt and item.excerpt in prompt
    assert "2026-10-07" in prompt or BUNDLE.as_of.isoformat() in prompt
    assert "Everything you know from elsewhere does not exist" in prompt
    assert "competition=not_searched" in prompt


# --- the reasoner -----------------------------------------------------------


def canned_llm() -> FakeLLM:
    mechanism = draft(
        claim(
            "KRAS G12C is a frequent, poor-prognosis driver in NSCLC",
            claim_type="target_causal",
            links=[link("E-0006", G12C)],
            critical=True,
        ),
        claim(
            "Binding mode differs from sotorasib and adagrasib",
            claim_type="target_causal",
            links=[link("E-0010", STRUCTURE)],
        ),
    )
    translation = draft(
        claim(
            "Divarasib produces confirmed responses in NSCLC patients",
            claim_type="drug_acts_in_humans",
            chain_link="biological_response",
            links=[link("E-0007", ORR)],
            critical=True,
        ),
        claim(
            "Target engagement in tumour tissue is not shown",
            claim_type="drug_acts_in_humans",
            chain_link="target_engagement",
            basis="unknown",
        ),
    )
    return FakeLLM({"reasoning.mechanism": mechanism, "reasoning.translation": translation})


def test_reasoner_satisfies_the_contract() -> None:
    assert isinstance(ModuleReasoner(canned_llm(), "R-1"), Reasoner)


def test_reasoner_returns_grounded_claims_with_computed_confidence() -> None:
    reasoner = ModuleReasoner(canned_llm(), "R-1")
    claims, links = reasoner.reason(BUNDLE)
    by_text = {c.text: c for c in claims}
    response = by_text["Divarasib produces confirmed responses in NSCLC patients"]
    assert response.confidence > 0.6  # peer-reviewed phase 1: strong for "acts in humans"
    in_vitro = by_text["Binding mode differs from sotorasib and adagrasib"]
    assert in_vitro.confidence < response.confidence  # one in vitro paper is weaker
    assert all(l.claim_id in {c.id for c in claims} for l in links)
    assert len(reasoner.trace.llm_results) == 2 and not reasoner.trace.drops


def test_missing_chain_links_become_explicit_unknown_claims() -> None:
    claims, _ = ModuleReasoner(canned_llm(), "R-1").reason(BUNDLE)
    chain = {c.chain_link: c for c in claims if c.chain_link}
    assert set(chain) == set(ChainLink)  # every link is spoken to, even if only as unknown
    exposure = chain[ChainLink.HUMAN_EXPOSURE]
    assert exposure.basis is Basis.UNKNOWN
    assert exposure.diligence_type is DiligenceType.PATIENT_LEVEL_DATA
    assert chain[ChainLink.TARGET_ENGAGEMENT].diligence_type is DiligenceType.EXPERIMENT


def test_end_to_end_a_thin_chain_cannot_reach_invest() -> None:
    claims, _ = ModuleReasoner(canned_llm(), "R-1").reason(BUNDLE)
    verdict = score_verdict(claims)
    assert verdict.verdict is Verdict.CONDITIONAL  # three of five links are unknown
    assert any(g.gate_id.value == "S1" and g.fired for g in verdict.gates)
    assert verdict.translation_chain_probability < 0.5


def test_a_model_that_invents_a_quote_cannot_raise_confidence() -> None:
    forged = draft(
        claim(
            "Divarasib is curative",
            claim_type="drug_acts_in_humans",
            chain_link="patient_benefit",
            links=[link("E-0007", "all patients were cured")],
        ),
    )
    llm = FakeLLM({"reasoning.mechanism": draft(), "reasoning.translation": forged})
    reasoner = ModuleReasoner(llm, "R-1")
    claims, links = reasoner.reason(BUNDLE)
    cured = next(c for c in claims if c.text == "Divarasib is curative")
    assert not [l for l in links if l.claim_id == cured.id]
    assert cured.basis is Basis.INFERRED and cured.confidence == pytest.approx(0.3)
    assert reasoner.trace.drops


def test_the_same_bundle_gives_the_same_claims() -> None:
    first = ModuleReasoner(canned_llm(), "R-1").reason(BUNDLE)
    second = ModuleReasoner(canned_llm(), "R-1").reason(BUNDLE)
    assert first == second
