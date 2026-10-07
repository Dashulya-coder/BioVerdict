"""B3: clinical and competition modules, on real recorded ClinicalTrials.gov records."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.connectors.clinicaltrials import parse_study
from bioverdict.llm import FakeLLM
from bioverdict.reasoning import ALL_MODULES, CLINICAL, COMPETITION, ModuleReasoner
from bioverdict.reasoning.gate_guards import evidence_guard
from bioverdict.reasoning.grounding import DropKind, resolve_claim_type
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.models import (
    Bundle,
    ClaimEvidenceLink,
    ClaimType,
    Direction,
    Evidence,
    EvidenceLevel,
    GateId,
    Section,
    SectionStatus,
    SourceKind,
    Verdict,
)

ROOT = Path(__file__).parents[3]
SEARCH = json.loads((ROOT / "fixtures/raw/clinicaltrials/search_terminated.json").read_text())
BASE = Bundle.model_validate_json((ROOT / "fixtures/bundles/divarasib.json").read_text())
RETRIEVED = datetime(2026, 10, 7, tzinfo=UTC)
AS_OF = date(2026, 10, 7)


def status_record(nct: str) -> Evidence:
    """The registry status evidence of a real recorded study."""
    study = next(
        s for s in SEARCH["studies"] if s["protocolSection"]["identificationModule"]["nctId"] == nct
    )
    return next(e for e in parse_study(study, RETRIEVED) if e.id.endswith(":status"))


FUTILITY = status_record("NCT04933695")  # whyStopped: "Futility"
BUSINESS = status_record("NCT04892017")  # "business decision, not based on any safety or efficacy"


def numbered(*items: Evidence) -> list[Evidence]:
    return [
        e.model_copy(update={"id": f"E-{i:04d}", "level": EvidenceLevel.REGISTRY_RECORD})
        if e.id.startswith("NCT")
        else e
        for i, e in enumerate(items, start=1)
    ]


def publication(eid: str, text: str, group: str, level=EvidenceLevel.HUMAN_INTERVENTIONAL):
    return Evidence(
        id=eid,
        source="PubMed",
        source_family="literature",
        source_kind=SourceKind.PEER_REVIEWED,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{eid[2:]}",
        excerpt=text,
        published_at=date(2025, 1, 1),
        retrieved_at=RETRIEVED,
        level=level,
        independence_group=group,
        version=1,
    )


def bundle_of(*items: Evidence) -> Bundle:
    return BASE.model_copy(
        update={
            "evidence": numbered(*items),
            "as_of": AS_OF,
            "section_statuses": {
                Section.CLINICAL: SectionStatus.FOUND,
                Section.COMPETITION: SectionStatus.FOUND,
            },
        }
    )


def pair(evidence: Evidence, direction: Direction = Direction.SUPPORTS):
    link = ClaimEvidenceLink(
        claim_id="C-1", evidence_id=evidence.id, direction=direction, quote=evidence.excerpt[:20]
    )
    return link, evidence


def draft_claim(text: str, evidence: list[Evidence], gates=(), **kw) -> dict:
    return {
        "text": text,
        "claim_type": "study_fact",
        "basis": "extracted",
        "gate_signals": list(gates),
        "links": [
            {"evidence_id": e.id, "direction": "supports", "quote": e.excerpt[:30]}
            for e in evidence
        ],
    } | kw


def run(bundle: Bundle, clinical: list[dict], competition=()):
    empty = ModuleDraft(claims=[])
    llm = FakeLLM(
        {
            "reasoning.mechanism": empty,
            "reasoning.clinical": ModuleDraft.model_validate({"claims": clinical}),
            "reasoning.competition": ModuleDraft.model_validate({"claims": list(competition)}),
            "reasoning.translation": empty,
        }
    )
    reasoner = ModuleReasoner(llm, "R-1")
    claims, links = reasoner.reason(bundle)
    return claims, links, reasoner


# --- the modules ------------------------------------------------------------------


def test_the_four_modules_run_in_the_planned_order() -> None:
    assert [m.name for m in ALL_MODULES] == ["mechanism", "clinical", "competition", "translation"]
    assert CLINICAL.allowed_gates == {GateId.K1, GateId.K2, GateId.K4}
    assert COMPETITION.allowed_gates == {GateId.S4}


def test_every_module_step_has_a_model_configured() -> None:
    from bioverdict.llm import LLMConfig

    config = LLMConfig.default()
    for module in ALL_MODULES:
        assert config.step(module.step).models


# --- gate guards on real registry records ---------------------------------------------


def test_k1_is_supported_by_a_real_futility_stop() -> None:
    (ev,) = numbered(FUTILITY)
    assert evidence_guard(GateId.K1, [pair(ev)]) is None


def test_k1_is_refused_for_a_business_stop_with_misleading_words() -> None:
    (ev,) = numbered(BUSINESS)
    why = evidence_guard(GateId.K1, [pair(ev)])
    assert why and "lack of efficacy" in why  # "not based on any safety or efficacy concerns"
    assert evidence_guard(GateId.K2, [pair(ev)])  # and it is no safety stop either


def test_k4_needs_a_terminated_or_withdrawn_study_or_a_discontinued_program() -> None:
    (ev,) = numbered(BUSINESS)
    assert evidence_guard(GateId.K4, [pair(ev)]) is None  # terminated: the sponsor stopped it
    active = publication("E-0100", "The study is recruiting patients in 40 sites.", "sponsor:X")
    assert evidence_guard(GateId.K4, [pair(active)])
    release = publication("E-0101", "The company has discontinued development of the asset.", "s")
    assert evidence_guard(GateId.K4, [pair(release)]) is None


def test_k2_needs_a_safety_stop_or_a_regulatory_safety_action() -> None:
    hold = publication("E-0102", "FDA placed a clinical hold after two deaths.", "g")
    assert evidence_guard(GateId.K2, [pair(hold)]) is None
    mild = publication("E-0103", "Grade 3 events occurred in 11% of patients.", "g")
    assert evidence_guard(GateId.K2, [pair(mild)])


def test_k3_needs_human_genetics_and_s4_needs_three_independent_sources() -> None:
    genetics = publication(
        "E-0104",
        "Loss of function carriers have shorter survival.",
        "g",
        EvidenceLevel.HUMAN_GENETICS,
    )
    assert evidence_guard(GateId.K3, [pair(genetics)]) is None
    assert evidence_guard(GateId.K3, [pair(publication("E-0105", "text", "g"))])
    same = [publication(f"E-02{i}", f"competitor {i} in phase 3", "sponsor:One") for i in range(3)]
    assert evidence_guard(GateId.S4, [pair(e) for e in same])  # one sponsor counts once
    three = [
        publication(f"E-03{i}", f"competitor {i} in phase 3", f"sponsor:{i}") for i in range(3)
    ]
    assert evidence_guard(GateId.S4, [pair(e) for e in three]) is None


# --- through the reasoner ------------------------------------------------------------


def test_a_k1_claim_on_a_business_stop_loses_the_gate_but_keeps_the_claim() -> None:
    bundle = bundle_of(BUSINESS)
    claims, _, reasoner = run(
        bundle, [draft_claim("The same target failed", bundle.evidence, gates=["K1"])]
    )
    (claim,) = [c for c in claims if c.section is Section.CLINICAL]
    assert claim.gate_signals == []
    gate_drops = [d for d in reasoner.trace.drops if d.kind is DropKind.GATE]
    assert gate_drops and "not supported by the cited evidence" in gate_drops[0].reason
    assert not score_verdict(claims).gates[0].fired


def test_one_futility_record_gives_an_unconfirmed_signal_not_do_not_invest() -> None:
    bundle = bundle_of(FUTILITY)
    claims, _, _ = run(
        bundle, [draft_claim("The same target failed for futility", bundle.evidence, gates=["K1"])]
    )
    (claim,) = [c for c in claims if c.gate_signals]
    assert claim.claim_type is ClaimType.STUDY_FACT
    assert 0.6 < claim.confidence < 0.85  # one registry record: about 0.77
    result = score_verdict(claims)
    assert result.verdict is Verdict.CONDITIONAL
    assert any("second independent source" in c for c in result.what_would_change_our_mind)


def test_a_second_independent_source_makes_k1_fire() -> None:
    paper = publication(
        "E-0050",
        "The trial was stopped for futility: it did not meet its primary endpoint.",
        "trial:NCT04933695",
    )
    bundle = bundle_of(FUTILITY, paper)
    claims, _, _ = run(
        bundle, [draft_claim("The same target failed for futility", bundle.evidence, gates=["K1"])]
    )
    result = score_verdict(claims)
    k1 = next(g for g in result.gates if g.gate_id is GateId.K1)
    assert k1.fired and result.verdict is Verdict.DO_NOT_INVEST


# --- study facts cannot pass for efficacy -----------------------------------------------


def test_a_study_fact_cannot_be_a_key_claim() -> None:
    bundle = bundle_of(FUTILITY)
    claims, _, reasoner = run(
        bundle, [draft_claim("The drug works", bundle.evidence, critical=True)]
    )
    (claim,) = [c for c in claims if c.section is Section.CLINICAL]
    assert claim.claim_type is ClaimType.STUDY_FACT and not claim.critical
    assert any(d.kind is DropKind.CRITICAL for d in reasoner.trace.drops)


def test_study_fact_is_not_allowed_outside_the_modules_that_describe_studies() -> None:
    assert resolve_claim_type(ClaimType.STUDY_FACT, [], None, allow_study_fact=False) is (
        ClaimType.DRUG_ACTS_IN_HUMANS
    )
    assert resolve_claim_type(ClaimType.STUDY_FACT, [], None, allow_study_fact=True) is (
        ClaimType.STUDY_FACT
    )


def test_a_protocol_description_cannot_make_an_efficacy_claim_confident() -> None:
    bundle = bundle_of(FUTILITY)  # registry_record evidence only
    claims, _, _ = run(
        bundle,
        [draft_claim("Divarasib is effective", bundle.evidence, claim_type="drug_acts_in_humans")],
    )
    (claim,) = [c for c in claims if c.section is Section.CLINICAL]
    assert claim.confidence == pytest.approx(0.5)  # the prior: the registry record weighs 0


# --- competition ---------------------------------------------------------------------------


def test_s4_survives_with_three_independent_competitors_only() -> None:
    sponsors = ["Amgen", "BMS", "Lilly"]
    items = [
        publication(f"E-00{i}", f"{s} competitor is in phase 3 for the same target", f"sponsor:{s}")
        for i, s in enumerate(sponsors, start=1)
    ]
    bundle = bundle_of(*items)
    competition = [
        draft_claim(
            "Three competitors with the same mechanism are in phase 3",
            bundle.evidence,
            gates=["S4"],
            claim_type="study_fact",
        )
    ]
    claims, _, _ = run(bundle, [], competition)
    assert [c.gate_signals for c in claims if c.section is Section.COMPETITION] == [[GateId.S4]]
    crowded = score_verdict(claims)
    assert next(g for g in crowded.gates if g.gate_id is GateId.S4).fired

    one = bundle_of(items[0])
    claims, _, reasoner = run(
        one,
        [],
        [draft_claim("A crowded class", one.evidence, gates=["S4"], claim_type="study_fact")],
    )
    assert [c.gate_signals for c in claims if c.section is Section.COMPETITION] == [[]]
    assert any("1 independent source" in d.reason for d in reasoner.trace.drops)


def test_a_k3_claim_needs_human_genetics_through_the_reasoner() -> None:
    animal = publication(
        "E-0001",
        "Knockout mice lacking the gene are healthy.",
        "lab:A",
        EvidenceLevel.ANIMAL_IN_VIVO,
    )
    human = publication(
        "E-0002",
        "Human carriers of loss of function variants have a shorter life.",
        "lab:B",
        EvidenceLevel.HUMAN_GENETICS,
    )

    def mechanism_claims(evidence: Evidence) -> list[Evidence]:
        bundle = BASE.model_copy(update={"evidence": [evidence]})
        draft = ModuleDraft.model_validate(
            {
                "claims": [
                    draft_claim("Genetics contradicts the direction", [evidence], gates=["K3"])
                ]
            }
        )
        empty = ModuleDraft(claims=[])
        llm = FakeLLM(
            {
                "reasoning.mechanism": draft,
                "reasoning.clinical": empty,
                "reasoning.competition": empty,
                "reasoning.translation": empty,
            }
        )
        claims, _ = ModuleReasoner(llm, "R-1").reason(bundle)
        return [c for c in claims if c.section is Section.MECHANISM]

    assert mechanism_claims(animal)[0].gate_signals == []  # a mouse is not human genetics
    assert mechanism_claims(human)[0].gate_signals == [GateId.K3]
