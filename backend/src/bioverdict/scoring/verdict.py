"""Kill criteria (gates) and the verdict rule. Pure code: same claims in, same verdict out.

The LLM only establishes facts and attaches evidence; a claim lists the gates it asserts in
`gate_signals`. Whether a gate fires is decided here, from the claim's computed confidence.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from bioverdict.scoring.confidence import apply_confidence, chain_probability
from bioverdict.scoring.config import ConfidenceConfig, VerdictConfig
from bioverdict.store.models import (
    Basis,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    Evidence,
    GateId,
    GateResult,
    Range,
    ServiceFlag,
    Verdict,
    VerdictResult,
)

GATE_TEXT: dict[GateId, str] = {
    GateId.K1: "The same target failed for efficacy in this indication, and the difference is unexplained",
    GateId.K2: "Serious on-target toxicity in humans with no way to mitigate it",
    GateId.K3: "Human genetics contradicts the direction of action",
    GateId.K4: "The sponsor stopped the program",
    GateId.K5: "rNPV is negative even in the optimistic (P90) scenario",
    GateId.S1: "A link of the human translation chain is missing",
    GateId.S2: "A key claim rests on too little evidence (sparse)",
    GateId.S3: "A key claim is contested: strong evidence both for and against",
    GateId.S4: "3 or more competitors with the same mechanism are ahead without a clear advantage",
    GateId.S5: "The biomarker or endpoint is not recognised by the regulator as a surrogate",
    GateId.S6: "IP protection ends soon after the expected launch, or ownership is unclear",
}
# What may assert a gate. A kill criterion needs a fact the evidence states (a quote, or a number
# derived from quotes); a soft one may also rest on a conclusion drawn from the evidence. Never a
# gap (`unknown`) or a guess (`hypothesis`).
_HARD_BASES = {Basis.EXTRACTED, Basis.DERIVED}
_SOFT_BASES = {*_HARD_BASES, Basis.INFERRED}

HARD = {GateId.K1, GateId.K2, GateId.K3, GateId.K4, GateId.K5}
_SIGNAL_ONLY = [GateId.K1, GateId.K2, GateId.K3, GateId.K4, GateId.S4, GateId.S5, GateId.S6]


def basis_can_assert(gate: GateId, basis: Basis) -> bool:
    return basis in (_HARD_BASES if gate in HARD else _SOFT_BASES)


def _enough_sources(gate: GateId, claim: Claim, vcfg: VerdictConfig) -> bool:
    """A hard gate needs evidence from at least `hard_gate_min_groups` independence groups.

    A claim without a computed breakdown (built by hand, as in tests) is not held to this.
    """
    if gate not in HARD or claim.confidence_parts is None:
        return True
    return claim.confidence_parts.independent_groups >= vcfg.hard_gate_min_groups


def _kind(gate: GateId) -> Literal["hard", "soft"]:
    return "hard" if gate in HARD else "soft"


def chain_confidences(claims: list[Claim]) -> list[float | None]:
    """Confidence per chain link, in chain order; the strongest claim speaks for a link."""
    return [
        max((c.confidence for c in claims if c.chain_link is link), default=None)
        for link in ChainLink
    ]


def evaluate_gates(
    claims: list[Claim], rnpv: Range | None, vcfg: VerdictConfig, ccfg: ConfidenceConfig
) -> tuple[list[GateResult], float, list[ChainLink]]:
    """Return gate results, translation-chain probability and the missing chain links."""
    results: list[GateResult] = []

    for gate in _SIGNAL_ONLY:  # gates asserted by a claim with enough confidence
        signals = [c for c in claims if gate in c.gate_signals and basis_can_assert(gate, c.basis)]
        threshold = vcfg.t_hard_gate if gate in HARD else vcfg.t_gate
        confident = [c for c in signals if c.confidence >= threshold]
        firing = [c for c in confident if _enough_sources(gate, c, vcfg)]
        near = [c for c in signals if vcfg.t_near <= c.confidence < threshold]
        if firing:
            near_miss = None
        elif confident:  # confident, but resting on one source only
            near_miss = (
                f"{gate.value} would fire if claim {confident[0].id} were confirmed by a second "
                f"independent source (all its evidence is from one: "
                f"{confident[0].confidence:.2f} is not enough on its own)"
            )
        elif near:
            near_miss = (
                f"{gate.value} would fire if claim {near[0].id} (confidence "
                f"{near[0].confidence:.2f}) reached {threshold:.2f}"
            )
        else:
            near_miss = None
        results.append(
            GateResult(
                gate_id=gate,
                kind=_kind(gate),
                fired=bool(firing),
                claim_ids=[c.id for c in firing],
                near_miss=near_miss,
            )
        )

    k5 = rnpv is not None and rnpv.p90 < 0  # needs the investment model's output
    results.append(GateResult(gate_id=GateId.K5, kind="hard", fired=k5))

    raw = chain_confidences(claims)
    # A link with no claim at all is treated as unknown: ai_inference-level confidence.
    link_conf = [ccfg.no_evidence_confidence if c is None else c for c in raw]
    chain_p, missing_idx = chain_probability(link_conf, ccfg)
    links = list(ChainLink)
    missing = [links[i] for i in missing_idx]
    results.append(
        GateResult(
            gate_id=GateId.S1,
            kind="soft",
            fired=bool(missing),
            claim_ids=[c.id for c in claims if c.chain_link in missing],
        )
    )

    critical = [c for c in claims if c.critical]
    for gate, flag in ((GateId.S2, ServiceFlag.SPARSE), (GateId.S3, ServiceFlag.CONTESTED)):
        hit = [c.id for c in critical if flag in c.flags]
        results.append(GateResult(gate_id=gate, kind="soft", fired=bool(hit), claim_ids=hit))

    order = list(GateId)
    results.sort(key=lambda r: order.index(r.gate_id))
    return results, chain_p, missing


def score_verdict(
    claims: list[Claim],
    rnpv: Range | None = None,
    vcfg: VerdictConfig | None = None,
    ccfg: ConfidenceConfig | None = None,
) -> VerdictResult:
    """Apply the plan's verdict rule. Claims must already carry their computed confidence.

    1. any hard gate fires -> Do Not Invest
    2. else any soft gate fires, or a hard gate has one source only -> Conditional
    3. else Invest if rNPV P50 > 0, chain probability >= 0.5 and key claims >= 0.7
    4. else Conditional, with the failed conditions listed
    """
    vcfg, ccfg = vcfg or VerdictConfig(), ccfg or ConfidenceConfig()
    gates, chain_p, _ = evaluate_gates(claims, rnpv, vcfg, ccfg)
    by_id = {c.id: c for c in claims}
    fired = [g for g in gates if g.fired]
    hard, soft = [g for g in fired if g.kind == "hard"], [g for g in fired if g.kind == "soft"]
    critical = [c for c in claims if c.critical]
    # A kill criterion backed by one source: too weak for Do Not Invest, too serious to ignore.
    unconfirmed = [
        g
        for g in gates
        if g.kind == "hard"
        and not g.fired
        and any(
            c.confidence >= vcfg.t_gate
            and g.gate_id in c.gate_signals
            and basis_can_assert(g.gate_id, c.basis)
            for c in claims
        )
    ]

    conditions: list[str] = []
    if hard:
        verdict = Verdict.DO_NOT_INVEST
    elif soft or unconfirmed:
        verdict = Verdict.CONDITIONAL
    else:
        if rnpv is None:
            conditions.append("rNPV is not available: Invest needs rNPV P50 > 0")
        elif rnpv.p50 <= vcfg.rnpv_p50_min:
            conditions.append(f"rNPV P50 is {rnpv.p50:,.0f}: Invest needs it above 0")
        if chain_p < vcfg.chain_min:
            conditions.append(
                f"translation chain probability is {chain_p:.2f}: Invest needs {vcfg.chain_min}"
            )
        if not critical:
            conditions.append("no key claim is marked critical: nothing to base Invest on")
        conditions += [
            f"key claim {c.id} has confidence {c.confidence:.2f}: Invest needs {vcfg.key_claim_min}"
            for c in critical
            if c.confidence < vcfg.key_claim_min
        ]
        verdict = Verdict.CONDITIONAL if conditions else Verdict.INVEST

    if hard:
        fired_conf = [by_id[i].confidence for g in hard for i in g.claim_ids if i in by_id]
        confidence = max(fired_conf, default=0.5)
    else:
        confidence = (
            sum(c.confidence for c in critical) / len(critical)
            if critical
            else vcfg.no_critical_confidence
        )

    risks = [GATE_TEXT[g.gate_id] for g in hard + soft]
    risks += [f"{GATE_TEXT[g.gate_id]} (not yet confirmed)" for g in unconfirmed]
    # A key claim is a positive statement; what makes it a risk is how little backs it.
    risks += [
        f"Key claim with limited support ({c.confidence:.0%}): {c.text}"
        for c in sorted(critical, key=lambda c: c.confidence)
        if c.confidence < vcfg.key_claim_min
    ]
    changes = [f"Resolving this would lift the cap: {GATE_TEXT[g.gate_id]}" for g in soft]
    changes += [
        f"Confirm or refute {g.gate_id.value} with a second independent source: "
        f"{GATE_TEXT[g.gate_id]}"
        for g in unconfirmed
    ]
    changes += conditions
    changes += [g.near_miss for g in gates if g.near_miss]

    return VerdictResult(
        verdict=verdict,
        confidence=confidence,
        gates=gates,
        translation_chain_probability=chain_p,
        rnpv=rnpv,
        top_risks=risks[:3],
        what_would_change_our_mind=changes,
    )


class DeterministicScorer:
    """`Scorer` contract implementation. `rnpv` comes from the investment model once it exists."""

    def __init__(
        self,
        rnpv: Range | None = None,
        vcfg: VerdictConfig | None = None,
        ccfg: ConfidenceConfig | None = None,
    ) -> None:
        self.rnpv, self.vcfg, self.ccfg = rnpv, vcfg, ccfg

    def score(self, claims: list[Claim], links: list[ClaimEvidenceLink]) -> VerdictResult:
        """Verdict from claims whose `confidence` is already computed.

        `links` is not read here: confidence comes from `apply_confidence` (or `rescore`). Claims
        carrying a stale confidence give a stale verdict, so after any evidence change call
        `rescore` instead.
        """
        return score_verdict(claims, self.rnpv, self.vcfg, self.ccfg)


def rescore(
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
    evidence: dict[str, Evidence],
    as_of: date,
    rnpv: Range | None = None,
    vcfg: VerdictConfig | None = None,
    ccfg: ConfidenceConfig | None = None,
) -> tuple[list[Claim], VerdictResult]:
    """Recompute every confidence from the evidence, then the verdict (incremental recompute)."""
    updated = apply_confidence(claims, links, evidence, as_of, ccfg)
    return updated, score_verdict(updated, rnpv, vcfg, ccfg)
