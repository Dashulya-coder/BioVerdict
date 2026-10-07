"""Gate guards on real recorded ClinicalTrials.gov records."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from bioverdict.connectors.clinicaltrials import parse_study
from bioverdict.llm import FakeLLM
from bioverdict.reasoning import MECHANISM, ModuleReasoner
from bioverdict.reasoning.gate_guards import evidence_guard
from bioverdict.reasoning.grounding import DropKind, ground_draft
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.store.models import (
    Bundle,
    ClaimEvidenceLink,
    Direction,
    Evidence,
    EvidenceLevel,
    GateId,
    Section,
    SourceKind,
)

ROOT = Path(__file__).parents[3]
SEARCH = json.loads((ROOT / "fixtures/raw/clinicaltrials/search_terminated.json").read_text())
BASE = Bundle.model_validate_json((ROOT / "fixtures/bundles/divarasib.json").read_text())
RETRIEVED = datetime(2026, 10, 7, tzinfo=UTC)


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


def pair(evidence: Evidence, direction: Direction = Direction.SUPPORTS):
    link = ClaimEvidenceLink(
        claim_id="C-1", evidence_id=evidence.id, direction=direction, quote=evidence.excerpt[:20]
    )
    return link, evidence


def draft_claim(text: str, evidence: list[Evidence], gates=(), **kw) -> dict:
    return {
        "text": text,
        "claim_type": "other",
        "basis": "extracted",
        "gate_signals": list(gates),
        "links": [
            {"evidence_id": e.id, "direction": "supports", "quote": e.excerpt[:30]}
            for e in evidence
        ],
    } | kw


# --- the guard itself -------------------------------------------------------------


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


# --- in grounding -----------------------------------------------------------------------


def ground(bundle: Bundle, claim: dict, gates: set[GateId]):
    return ground_draft(
        ModuleDraft.model_validate({"claims": [claim]}),
        bundle,
        "R-1",
        Section.CLINICAL,
        allowed_gates=frozenset(gates),
        gate_guard=evidence_guard,
    )


def test_a_k1_claim_on_a_business_stop_loses_the_gate_but_keeps_the_claim() -> None:
    bundle = BASE.model_copy(update={"evidence": numbered(BUSINESS)})
    g = ground(bundle, draft_claim("The same target failed", bundle.evidence, ["K1"]), {GateId.K1})
    assert len(g.claims) == 1 and g.claims[0].gate_signals == []
    drops = [d for d in g.drops if d.kind is DropKind.GATE]
    assert drops and "not supported by the cited evidence" in drops[0].reason


def test_a_k1_claim_on_a_futility_stop_keeps_the_gate() -> None:
    bundle = BASE.model_copy(update={"evidence": numbered(FUTILITY)})
    g = ground(bundle, draft_claim("The same target failed", bundle.evidence, ["K1"]), {GateId.K1})
    assert g.claims[0].gate_signals == [GateId.K1]
    assert not [d for d in g.drops if d.kind is DropKind.GATE]


def test_without_a_guard_the_signal_is_kept_as_before() -> None:
    bundle = BASE.model_copy(update={"evidence": numbered(BUSINESS)})
    g = ground_draft(
        ModuleDraft.model_validate({"claims": [draft_claim("x", bundle.evidence, ["K1"])]}),
        bundle,
        "R-1",
        Section.CLINICAL,
        allowed_gates=frozenset({GateId.K1}),
    )
    assert g.claims[0].gate_signals == [GateId.K1]


# --- the mechanism module uses the K3 guard through the reasoner ---------------------------


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

    def mechanism_gates(evidence: Evidence) -> list[GateId]:
        bundle = BASE.model_copy(update={"evidence": [evidence]})
        draft = ModuleDraft.model_validate(
            {"claims": [draft_claim("Genetics contradicts the direction", [evidence], ["K3"])]}
        )
        reasoner = ModuleReasoner(
            FakeLLM({"reasoning.mechanism": draft}), "R-1", modules=(MECHANISM,)
        )
        claims, _ = reasoner.reason(bundle)
        return claims[0].gate_signals

    assert mechanism_gates(animal) == []  # a mouse is not human genetics
    assert mechanism_gates(human) == [GateId.K3]
