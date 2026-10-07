"""The reasoning modules. Domain knowledge lives here as checklists, not in the core (ADR-006)."""

from __future__ import annotations

from dataclasses import dataclass

from bioverdict.reasoning.gate_guards import GateGuard, evidence_guard
from bioverdict.store.models import ClaimType, GateId, Section

_MECHANISM = """\
Mechanism and biological validation. Decide whether the target is causal for the disease or only
correlated with it, using whatever the evidence offers: human genetics, disease tissue, target
expression, pathway biology, perturbation studies, animal models, prior drugs against the target.
- claim_type is "target_causal" for statements about the target and the disease.
- Say whether each piece of support is causal (genetics, perturbation, an effective prior drug)
  or correlational (expression, association).
- Actively look for contradicting evidence: a prior drug against this target that failed, human
  genetics pointing the other way, an effect that is not target-specific.
- If human loss-of-function genetics shows harm while the drug mimics that loss, or the direction
  of action is contradicted by genetics, add gate signal K3 to that claim.
- If an area has no evidence, write an `unknown` claim for it instead of leaving it out.
"""

_TRANSLATION = """\
Preclinical-to-human translation. Build the chain, one or more claims per link, and set
chain_link on every claim:
1. molecular_effect: the molecule modulates the target as intended (claim_type "drug_acts_in_humans").
2. human_exposure: an effective exposure is reachable in humans, compared with the exposure that
   worked experimentally (claim_type "drug_acts_in_humans").
3. target_engagement: the drug engages the target in the relevant tissue, including PK/PD and
   tissue penetration (claim_type "drug_acts_in_humans").
4. biological_response: engagement produces the expected biological response or biomarker change
   (claim_type "drug_acts_in_humans").
5. patient_benefit: the response gives clinical benefit within an acceptable therapeutic window
   (claim_type "drug_acts_in_humans").
- A link the evidence does not show is an `unknown` claim with its diligence_type. Do not bridge
  a missing link with an assumption; missing links are a finding.
- Response in patients is not proof of target engagement: say so when only the response is shown.
- Actively look for contradicting evidence and for dose or tolerability limits.
"""


@dataclass(frozen=True)
class ReasoningModule:
    name: str
    section: Section
    step: str  # LLM step name, so each module can have its own model and canned test answer
    instruction: str
    allowed_gates: frozenset[GateId] = frozenset()
    chain: bool = False  # claims carry a translation-chain link
    # The type is fixed by the module, not chosen by the model: it picks the evidence weights, so
    # a model that mislabels a claim could otherwise move its confidence (see grounding.py).
    claim_type: ClaimType | None = None
    # Code check that a gate signal rests on the right kind of evidence (reasoning/gate_guards.py).
    gate_guard: GateGuard | None = None


MECHANISM = ReasoningModule(
    name="mechanism",
    section=Section.MECHANISM,
    step="reasoning.mechanism",
    instruction=_MECHANISM,
    allowed_gates=frozenset({GateId.K3}),
    claim_type=ClaimType.TARGET_CAUSAL,
    gate_guard=evidence_guard,
)
TRANSLATION = ReasoningModule(
    name="translation",
    section=Section.TRANSLATION,
    step="reasoning.translation",
    instruction=_TRANSLATION,
    chain=True,
    claim_type=ClaimType.DRUG_ACTS_IN_HUMANS,
)
