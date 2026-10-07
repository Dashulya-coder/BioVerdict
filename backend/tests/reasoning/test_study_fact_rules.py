"""`study_fact` is the one claim type a registry record supports fully; keep it to study facts."""

from pathlib import Path

import pytest

from bioverdict.reasoning.grounding import DropKind, ground_draft, resolve_claim_type
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.store.models import Bundle, ClaimType, GateId, Section

BASE = Bundle.model_validate_json(
    (Path(__file__).parents[3] / "fixtures/bundles/divarasib.json").read_text()
)


def draft(**kw) -> ModuleDraft:
    claim = {"text": "A trial of the drug exists", "claim_type": "study_fact", "basis": "unknown"}
    return ModuleDraft.model_validate({"claims": [claim | kw]})


def ground(bundle: Bundle, d: ModuleDraft, **kw):
    return ground_draft(d, bundle, "R-1", Section.CLINICAL, **kw)


def test_study_fact_is_not_allowed_outside_the_modules_that_describe_studies() -> None:
    assert resolve_claim_type(ClaimType.STUDY_FACT, [], None) is ClaimType.DRUG_ACTS_IN_HUMANS
    assert resolve_claim_type(ClaimType.STUDY_FACT, [], None, allow_study_fact=False) is (
        ClaimType.DRUG_ACTS_IN_HUMANS
    )
    assert resolve_claim_type(ClaimType.STUDY_FACT, [], None, allow_study_fact=True) is (
        ClaimType.STUDY_FACT
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_a_gate_claim_is_a_study_fact_except_k3(allowed: bool) -> None:
    assert resolve_claim_type(ClaimType.OTHER, [GateId.K1], None, allowed) is ClaimType.STUDY_FACT
    assert resolve_claim_type(ClaimType.OTHER, [GateId.K3], None, allowed) is (
        ClaimType.TARGET_CAUSAL
    )


def test_a_study_fact_cannot_be_a_key_claim() -> None:
    g = ground(BASE, draft(critical=True), allow_study_fact=True)
    (claim,) = g.claims
    assert claim.claim_type is ClaimType.STUDY_FACT and not claim.critical
    assert any(d.kind is DropKind.CRITICAL for d in g.drops)


def test_the_same_claim_where_study_fact_is_not_allowed_may_stay_critical() -> None:
    g = ground(BASE, draft(critical=True), allow_study_fact=False)
    (claim,) = g.claims
    assert claim.claim_type is ClaimType.DRUG_ACTS_IN_HUMANS and claim.critical


def test_a_gate_claim_is_never_critical() -> None:
    g = ground(
        BASE,
        draft(critical=True, gate_signals=["K4"]),
        allowed_gates=frozenset({GateId.K4}),
        allow_study_fact=True,
    )
    (claim,) = g.claims
    assert claim.claim_type is ClaimType.STUDY_FACT and not claim.critical
