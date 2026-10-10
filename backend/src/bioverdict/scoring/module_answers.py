"""The answer of each of the six underwriting modules, computed by code from its claims.

A module's claims say what was found; this file says what they add up to. Every claim carries an
`implication` (what it means for an investor if true) and a confidence computed from its
evidence, so a module's answer is a weighted balance that anyone can recompute by hand, and a
change of the answer traces back to the claims that moved and the evidence that moved them.

The verdict does not read these answers: it follows from the gates and the investment model
(`scoring/verdict.py`). The sixth module, investment underwriting, reports that verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from bioverdict.scoring.verdict import GATE_TEXT
from bioverdict.store.models import (
    Basis,
    Claim,
    ClaimEvidenceLink,
    Implication,
    Section,
    Verdict,
    VerdictResult,
)


class ModuleId(StrEnum):
    UNMET_NEED = "disease_unmet_need"
    MECHANISM = "mechanism_validation"
    TRANSLATION = "preclinical_translation"
    CLINICAL = "clinical_development"
    COMPETITIVE_COMMERCIAL = "competitive_commercial"
    INVESTMENT = "investment_underwriting"


class ModuleAnswer(StrEnum):
    SUPPORTS = "supports"  # what the module found speaks for investing
    MIXED = "mixed"
    AGAINST = "against"
    INSUFFICIENT = "insufficient"  # too little evidence to say either way


@dataclass(frozen=True)
class ModuleSpec:
    module: ModuleId
    title: str
    question: str
    sections: tuple[Section, ...]


SPECS: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        ModuleId.UNMET_NEED,
        "Disease and unmet need",
        "Is the disease serious, and do today's treatments leave a need?",
        (Section.UNMET_NEED,),
    ),
    ModuleSpec(
        ModuleId.MECHANISM,
        "Mechanism and biological validation",
        "Is the target causal for the disease?",
        (Section.MECHANISM,),
    ),
    ModuleSpec(
        ModuleId.TRANSLATION,
        "Preclinical to human translation",
        "Does the effect carry over from the laboratory to patients?",
        (Section.TRANSLATION,),
    ),
    ModuleSpec(
        ModuleId.CLINICAL,
        "Clinical development",
        "Does the clinical record support taking the program forward?",
        (Section.CLINICAL, Section.FLAGS),
    ),
    ModuleSpec(
        ModuleId.COMPETITIVE_COMMERCIAL,
        "Competitive and commercial analysis",
        "Is there room to win against the competition, and a market to win?",
        (Section.COMPETITION, Section.COMMERCIAL, Section.IP_REGULATORY),
    ),
)
INVESTMENT_SPEC = ModuleSpec(
    ModuleId.INVESTMENT,
    "Investment underwriting",
    "Should we invest?",
    (Section.INVESTMENT,),
)
TITLES: dict[ModuleId, str] = {spec.module: spec.title for spec in (*SPECS, INVESTMENT_SPEC)}


class ModuleConfig(BaseModel):
    """Starting heuristics, not calibrated: change them only with a logged reason (scoring.md)."""

    model_config = ConfigDict(extra="forbid")

    min_weight: float = 0.2  # less total weight than this: not enough evidence to answer
    lean: float = 0.25  # |balance| at or above this is an answer; below it the module is mixed
    drivers: int = 5  # the claims shown as deciding the answer


@dataclass(frozen=True)
class Driver:
    """One claim's pull on its module: positive speaks for investing, negative against."""

    claim_id: str
    contribution: float


@dataclass(frozen=True)
class ModuleResult:
    module: ModuleId
    title: str
    question: str
    answer: ModuleAnswer
    headline: str
    balance: float | None  # -1 (all against) .. +1 (all for); None without weighted claims
    favourable: float
    unfavourable: float
    claim_ids: list[str] = field(default_factory=list)
    drivers: list[Driver] = field(default_factory=list)
    unknown_count: int = 0
    evidence_count: int = 0
    gates: list[str] = field(default_factory=list)  # fired gates that rest on this module


def contribution(claim: Claim) -> float:
    """How far a claim pulls its module, from its implication and its computed confidence.

    `2 * confidence - 1` is positive when the evidence makes the claim likely and negative when
    contradicting evidence outweighs the support, so a favourable claim that new evidence refutes
    ends up counting against. A claim with no weighted evidence (a gap, a hypothesis, a quote
    whose level carries no weight) pulls nowhere: its low confidence is ignorance, not refutation.
    """
    if claim.implication is Implication.NEUTRAL:
        return 0.0
    if claim.basis in (Basis.UNKNOWN, Basis.HYPOTHESIS):
        return 0.0
    parts = claim.confidence_parts
    if parts is not None and parts.support == 0 and parts.contra == 0:
        return 0.0
    sign = 1.0 if claim.implication is Implication.FAVOURABLE else -1.0
    return sign * (2 * claim.confidence - 1)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _section_module(
    spec: ModuleSpec,
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
    result: VerdictResult,
    cfg: ModuleConfig,
) -> ModuleResult:
    mine = [c for c in claims if c.section in spec.sections]
    ids = {c.id for c in mine}
    pulls = {c.id: contribution(c) for c in mine}
    favourable = sum(p for p in pulls.values() if p > 0)
    unfavourable = -sum(p for p in pulls.values() if p < 0)
    total = favourable + unfavourable
    balance = (favourable - unfavourable) / total if total >= cfg.min_weight else None
    unknowns = sum(c.basis is Basis.UNKNOWN for c in mine)

    fired = [g for g in result.gates if g.fired and ids.intersection(g.claim_ids)]
    hard = [g for g in fired if g.kind == "hard"]
    soft = [g for g in fired if g.kind == "soft"]
    weights = f"favourable weight {favourable:.2f} against unfavourable {unfavourable:.2f}"

    if hard:
        answer = ModuleAnswer.AGAINST
        headline = "; ".join(
            f"{g.gate_id.value} fired on {', '.join(i for i in g.claim_ids if i in ids)}: "
            f"{GATE_TEXT[g.gate_id]}"
            for g in hard
        )
    elif balance is None:
        answer = ModuleAnswer.INSUFFICIENT
        headline = (
            f"No claim here rests on weighted evidence either way ({_plural(unknowns, 'open gap')})"
            if mine
            else "Nothing was found for this module"
        )
    elif balance <= -cfg.lean:
        answer, headline = ModuleAnswer.AGAINST, f"The evidence weighs against: {weights}"
    elif balance >= cfg.lean and soft:
        answer = ModuleAnswer.MIXED
        headline = (
            f"The evidence is favourable ({weights}), but "
            + "; ".join(f"{g.gate_id.value}: {GATE_TEXT[g.gate_id]}" for g in soft).lower()
        )
    elif balance >= cfg.lean:
        answer, headline = ModuleAnswer.SUPPORTS, f"The evidence supports the case: {weights}"
    else:
        answer, headline = ModuleAnswer.MIXED, f"The evidence points both ways: {weights}"
    if unknowns and balance is not None:
        headline += f"; {_plural(unknowns, 'open gap')}"

    ranked = sorted((c for c in mine if pulls[c.id]), key=lambda c: (-abs(pulls[c.id]), c.id))
    return ModuleResult(
        module=spec.module,
        title=spec.title,
        question=spec.question,
        answer=answer,
        headline=headline,
        balance=balance,
        favourable=favourable,
        unfavourable=unfavourable,
        claim_ids=[c.id for c in mine],
        drivers=[Driver(c.id, pulls[c.id]) for c in ranked[: cfg.drivers]],
        unknown_count=unknowns,
        evidence_count=len({link.evidence_id for link in links if link.claim_id in ids}),
        gates=[g.gate_id.value for g in fired],
    )


_VERDICT_ANSWER = {
    Verdict.INVEST: ModuleAnswer.SUPPORTS,
    Verdict.CONDITIONAL: ModuleAnswer.MIXED,
    Verdict.DO_NOT_INVEST: ModuleAnswer.AGAINST,
}


def _investment_module(
    claims: list[Claim], links: list[ClaimEvidenceLink], result: VerdictResult, cfg: ModuleConfig
) -> ModuleResult:
    """The verdict as the answer of the last module, with the claims it was decided on."""
    fired = [g for g in result.gates if g.fired]
    gate_claims = [i for g in fired for i in g.claim_ids]
    key = [c.id for c in claims if c.critical]
    ids = list(dict.fromkeys([*gate_claims, *key]))
    by_id = {c.id: c for c in claims}
    pulls = {i: contribution(by_id[i]) for i in ids if i in by_id}
    if fired:
        reason = "gates fired: " + ", ".join(g.gate_id.value for g in fired)
    elif result.verdict is Verdict.INVEST:
        reason = "no gate fired and every condition of the rule holds"
    else:
        reason = "no gate fired, but a condition of the rule fails"
    numbers = []
    if result.pos is not None:
        numbers.append(f"probability of success {result.pos.p50:.0%} (P50, modeled)")
    if result.rnpv is not None:
        numbers.append(f"rNPV ${result.rnpv.p50 / 1e6:,.0f}M (P50, modeled)")
    headline = f"{result.verdict.value}: {reason}"
    if numbers:
        headline += "; " + ", ".join(numbers)
    ranked = sorted((i for i in pulls if pulls[i]), key=lambda i: (-abs(pulls[i]), i))
    favourable = sum(p for p in pulls.values() if p > 0)
    unfavourable = -sum(p for p in pulls.values() if p < 0)
    total = favourable + unfavourable
    return ModuleResult(
        module=INVESTMENT_SPEC.module,
        title=INVESTMENT_SPEC.title,
        question=INVESTMENT_SPEC.question,
        answer=_VERDICT_ANSWER[result.verdict],
        headline=headline,
        balance=(favourable - unfavourable) / total if total >= cfg.min_weight else None,
        favourable=favourable,
        unfavourable=unfavourable,
        claim_ids=ids,
        drivers=[Driver(i, pulls[i]) for i in ranked[: cfg.drivers]],
        unknown_count=sum(by_id[i].basis is Basis.UNKNOWN for i in ids if i in by_id),
        evidence_count=len({link.evidence_id for link in links if link.claim_id in set(ids)}),
        gates=[g.gate_id.value for g in fired],
    )


def module_answers(
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
    result: VerdictResult,
    cfg: ModuleConfig | None = None,
) -> list[ModuleResult]:
    """The six modules in report order. Same claims and verdict in, same answers out."""
    cfg = cfg or ModuleConfig()
    return [
        *(_section_module(spec, claims, links, result, cfg) for spec in SPECS),
        _investment_module(claims, links, result, cfg),
    ]
