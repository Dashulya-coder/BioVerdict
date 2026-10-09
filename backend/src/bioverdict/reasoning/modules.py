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


_CLINICAL = """\
Clinical development. From the registry records, published trials and company statements in the
evidence, establish: the target patient population, the endpoint, the biomarker strategy, the
comparator, the approximate trial size, the development sequence, and the relevant historical
trials. Then identify similar programs (same target, pathway or indication) that succeeded or
failed and explain what each implies for this program.
- Registry text states what a trial planned or what its status is; it is not a result. Use posted
  results, publications and company statements for what a trial found.
- Report response rates with their confirmation status when the evidence gives it, and say when
  two trials used different comparators or populations and so cannot be compared directly.
- Kill criteria. These claims describe a fact about studies or programs; assert a gate only when
  the cited evidence itself states the fact, and quote the words that state it:
  K1: the SAME target failed in a Phase 2 or 3 trial in this indication for lack of efficacy
      (futility, endpoint not met), and nothing in the evidence explains why this program
      differs (exposure, patient selection, modality). A trial stopped for a business decision,
      slow enrollment, funding or the pandemic is NOT a failed target: do not use K1 for it.
  K2: serious on-target toxicity in humans that cannot be mitigated (a clinical hold, deaths
      attributed to the drug, a boxed warning in the class).
  K4: the sponsor stopped this asset's program (a terminated or withdrawn study, a statement
      that development was discontinued).
- Write these gate claims about one fact each, and give each its own supporting quote. If a stop
  reason is missing or ambiguous, write a normal claim or an `unknown`, not a gate claim.
- If a part is missing from the evidence (no posted results, no comparator named), write an
  `unknown` claim for it.
"""

_COMPETITION = """\
Competition and pipeline. Map, from the evidence only: approved therapies; clinical-stage
competitors; other programs against the same target; alternative mechanisms in the same
indication; discontinued programs. For each competitor give its sponsor, its phase and the quote
that shows both. Say what differentiation a new entrant would need.
- Do not name a competitor the evidence does not name. The registry and the target databases in
  the bundle are samples, not a complete census: say so when the evidence is thin, and write an
  `unknown` claim if a part of the landscape was not searched.
- S4: at least three competitors with the same mechanism are a phase or more ahead of this
  program and show no clear disadvantage. Assert S4 on one claim that cites a separate piece of
  evidence for each competitor (different sponsors); one sponsor or one paper counts once.
- Distinguish a scientifically interesting program from a commercially valuable one: a crowded
  class matters even when the biology is sound.
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
    # Only modules that describe studies and programs may type a claim `study_fact`.
    allow_study_fact: bool = False
    # The source families this module reads. Market records are for code (market/tam.py) and are
    # never shown to a model; None means everything.
    families: frozenset[str] | None = None


MECHANISM = ReasoningModule(
    name="mechanism",
    section=Section.MECHANISM,
    step="reasoning.mechanism",
    instruction=_MECHANISM,
    allowed_gates=frozenset({GateId.K3}),
    claim_type=ClaimType.TARGET_CAUSAL,
    gate_guard=evidence_guard,
    families=frozenset({"target_database", "literature"}),
)
TRANSLATION = ReasoningModule(
    name="translation",
    section=Section.TRANSLATION,
    step="reasoning.translation",
    instruction=_TRANSLATION,
    chain=True,
    claim_type=ClaimType.DRUG_ACTS_IN_HUMANS,
    families=frozenset({"literature", "registry"}),
)

CLINICAL = ReasoningModule(
    name="clinical",
    section=Section.CLINICAL,
    step="reasoning.clinical",
    instruction=_CLINICAL,
    allowed_gates=frozenset({GateId.K1, GateId.K2, GateId.K4}),
    gate_guard=evidence_guard,
    allow_study_fact=True,
    families=frozenset({"registry", "literature"}),
)
COMPETITION = ReasoningModule(
    name="competition",
    section=Section.COMPETITION,
    step="reasoning.competition",
    instruction=_COMPETITION,
    allowed_gates=frozenset({GateId.S4}),
    gate_guard=evidence_guard,
    allow_study_fact=True,
    families=frozenset({"registry", "target_database"}),
)

# Order of the plan: translation reads what mechanism and clinical established.
ALL_MODULES = (MECHANISM, CLINICAL, COMPETITION, TRANSLATION)
