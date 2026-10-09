"""Turn a model draft into claims: grounded or dropped.

Rules (docs/architecture.md, verification gates 1 and 2):
- a link must name evidence that is in the bundle and quote it verbatim; otherwise it is dropped;
- a claim that says `extracted` but keeps no grounded link becomes `inferred`;
- an `unknown` claim always carries a diligence type;
- gate signals outside the module's remit and chain links outside the translation module are
  removed, and every removal is returned so it can be logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from bioverdict.reasoning.gate_guards import GateGuard
from bioverdict.reasoning.schemas import DraftClaim, ModuleDraft
from bioverdict.scoring.verdict import basis_can_assert
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    ClaimType,
    DiligenceType,
    Direction,
    Evidence,
    GateId,
    Section,
    SectionStatus,
)

# A quote shorter than this proves nothing ("a" is a substring of almost any text) unless it is
# the whole excerpt, as a short registry status can be.
MIN_QUOTE_CHARS = 8

# What kind of data would answer an unknown chain link (docs: "recognise what needs proprietary
# data rather than inventing an answer").
DEFAULT_DILIGENCE: dict[ChainLink, DiligenceType] = {
    ChainLink.MOLECULAR_EFFECT: DiligenceType.EXPERIMENT,
    ChainLink.HUMAN_EXPOSURE: DiligenceType.PATIENT_LEVEL_DATA,
    ChainLink.TARGET_ENGAGEMENT: DiligenceType.EXPERIMENT,
    ChainLink.BIOLOGICAL_RESPONSE: DiligenceType.PATIENT_LEVEL_DATA,
    ChainLink.PATIENT_BENEFIT: DiligenceType.PATIENT_LEVEL_DATA,
}
CHAIN_TEXT: dict[ChainLink, str] = {
    ChainLink.MOLECULAR_EFFECT: "the molecule modulates its target as intended",
    ChainLink.HUMAN_EXPOSURE: "the drug reaches an effective exposure in humans",
    ChainLink.TARGET_ENGAGEMENT: "the drug engages its target in the relevant human tissue",
    ChainLink.BIOLOGICAL_RESPONSE: "target engagement produces the expected biological response",
    ChainLink.PATIENT_BENEFIT: "the biological response gives a clinical benefit to patients",
}


class DropKind(StrEnum):
    """What code did to a model proposal. Callers branch on this, never on the reason text."""

    EMPTY_CLAIM = "empty_claim"  # a claim without text
    LINK = "link"  # a citation removed: unknown evidence, empty, too short or ungrounded quote
    DUPLICATE_LINK = "duplicate_link"  # the same evidence cited twice (harmless)
    BASIS = "basis"  # `extracted` without a grounded quote, now `inferred`
    CLAIM_TYPE = "claim_type"  # the model's claim type replaced by the module's or gate's
    GATE = "gate"  # a gate signal outside the module's remit
    CHAIN_LINK = "chain_link"  # a chain link outside the translation module
    CRITICAL = "critical"  # more critical claims than allowed


@dataclass(frozen=True)
class Drop:
    """Something the model proposed and code removed or changed, with the reason.

    Feeds verification_log and the trace. `what` names the thing (an evidence id, a gate, ...).
    """

    claim_id: str
    what: str
    reason: str
    kind: DropKind

    @property
    def is_citation_failure(self) -> bool:
        """True when the claim's support was weakened: a citation was rejected or basis lowered."""
        return self.kind in (DropKind.LINK, DropKind.BASIS)


@dataclass
class Grounded:
    claims: list[Claim] = field(default_factory=list)
    links: list[ClaimEvidenceLink] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)


TRANSLATION_SOURCES = (Section.CLINICAL, Section.MECHANISM)  # what the translation chain reads


def _unknown_status(bundle: Bundle, sections: tuple[Section, ...]) -> SectionStatus:
    """`not_searched` if none of the sections the claim depends on was searched, else `none_found`."""
    searched = any(
        bundle.section_statuses.get(s, SectionStatus.NOT_SEARCHED) is not SectionStatus.NOT_SEARCHED
        for s in sections
    )
    return SectionStatus.NONE_FOUND if searched else SectionStatus.NOT_SEARCHED


def ground_draft(
    draft: ModuleDraft,
    bundle: Bundle,
    run_id: str,
    section: Section,
    *,
    allowed_gates: frozenset[GateId] = frozenset(),
    allow_chain: bool = False,
    evidence_sections: tuple[Section, ...] | None = None,
    forced_type: ClaimType | None = None,
    gate_guard: GateGuard | None = None,
    allow_study_fact: bool = False,
    first_number: int = 1,
) -> Grounded:
    out = Grounded()
    evidence = bundle.evidence_by_id()
    number = first_number

    for item in draft.claims:
        if not item.text.strip():
            out.drops.append(Drop("-", "claim", "empty text", DropKind.EMPTY_CLAIM))
            continue
        claim_id = f"C-{number:04d}"
        number += 1

        links, seen = [], set()
        for link in item.links:
            ev = evidence.get(link.evidence_id)
            quote = link.quote.strip()
            if ev is None:
                out.drops.append(
                    Drop(claim_id, link.evidence_id, "evidence is not in the bundle", DropKind.LINK)
                )
            elif not quote:
                out.drops.append(Drop(claim_id, link.evidence_id, "empty quote", DropKind.LINK))
            elif len(quote) < MIN_QUOTE_CHARS and quote != ev.excerpt.strip():
                out.drops.append(
                    Drop(
                        claim_id,
                        link.evidence_id,
                        f"quote shorter than {MIN_QUOTE_CHARS} characters",
                        DropKind.LINK,
                    )
                )
            elif quote not in ev.excerpt:
                out.drops.append(
                    Drop(claim_id, link.evidence_id, "quote is not in the excerpt", DropKind.LINK)
                )
            elif link.evidence_id in seen:
                out.drops.append(
                    Drop(
                        claim_id, link.evidence_id, "evidence cited twice", DropKind.DUPLICATE_LINK
                    )
                )
            else:
                seen.add(link.evidence_id)
                links.append(
                    ClaimEvidenceLink(
                        claim_id=claim_id,
                        evidence_id=link.evidence_id,
                        direction=link.direction,
                        quote=quote,
                    )
                )

        out.claims.append(
            _build_claim(
                item,
                claim_id,
                run_id,
                section,
                any(l.direction is not Direction.NEUTRAL for l in links),
                bundle,
                out,
                allowed_gates,
                allow_chain,
                evidence_sections or (section,),
                forced_type,
                [
                    (link, evidence[link.evidence_id])
                    for link in links
                    if link.direction is Direction.SUPPORTS
                ],
                gate_guard,
                allow_study_fact,
            )
        )
        out.links.extend(links)
    return out


def _build_claim(
    item: DraftClaim,
    claim_id: str,
    run_id: str,
    section: Section,
    has_links: bool,
    bundle: Bundle,
    out: Grounded,
    allowed_gates: frozenset[GateId],
    allow_chain: bool,
    evidence_sections: tuple[Section, ...],
    forced_type: ClaimType | None,
    support: list[tuple[ClaimEvidenceLink, Evidence]],
    gate_guard: GateGuard | None,
    allow_study_fact: bool,
) -> Claim:
    gates: list[GateId] = []
    for g in item.gate_signals:
        if g not in allowed_gates:
            out.drops.append(
                Drop(claim_id, g.value, "gate is outside this module's remit", DropKind.GATE)
            )
        elif gate_guard is not None and (why := gate_guard(g, support)) is not None:
            out.drops.append(
                Drop(
                    claim_id,
                    g.value,
                    f"gate not supported by the cited evidence: {why}",
                    DropKind.GATE,
                )
            )
        else:
            gates.append(g)

    chain_link = item.chain_link if allow_chain else None
    if item.chain_link is not None and not allow_chain:
        out.drops.append(
            Drop(
                claim_id,
                item.chain_link.value,
                "chain link outside translation",
                DropKind.CHAIN_LINK,
            )
        )

    claim_type = resolve_claim_type(item.claim_type, gates, forced_type, allow_study_fact)
    if claim_type is not item.claim_type:
        out.drops.append(
            Drop(
                claim_id,
                "claim_type",
                f"set by code to {claim_type.value} (model: {item.claim_type.value})",
                DropKind.CLAIM_TYPE,
            )
        )

    critical = item.critical
    if critical and claim_type is ClaimType.STUDY_FACT:
        critical = False
        out.drops.append(
            Drop(
                claim_id,
                "critical",
                "a fact about a study cannot be a key claim: key claims need results",
                DropKind.CRITICAL,
            )
        )

    basis, diligence, status = Basis(item.basis), item.diligence_type, SectionStatus.FOUND
    if basis is Basis.EXTRACTED and not has_links:
        basis = Basis.INFERRED
        out.drops.append(
            Drop(
                claim_id,
                "basis",
                "extracted without a grounded supporting or contradicting quote: now inferred",
                DropKind.BASIS,
            )
        )
    kept = []
    for g in gates:
        if basis_can_assert(g, basis):
            kept.append(g)
        else:
            out.drops.append(
                Drop(
                    claim_id,
                    g.value,
                    f"a {basis.value} claim cannot assert a gate",
                    DropKind.GATE,
                )
            )
    gates = kept

    if basis is Basis.UNKNOWN:
        diligence = diligence or (
            DEFAULT_DILIGENCE[chain_link] if chain_link else DiligenceType.PROPRIETARY_DATA
        )
        status = _unknown_status(bundle, evidence_sections)

    return Claim(
        id=claim_id,
        run_id=run_id,
        section=section,
        text=item.text.strip(),
        claim_type=claim_type,
        basis=basis,
        status=status,
        confidence=0.0,  # computed from the evidence by scoring.apply_confidence
        chain_link=chain_link,
        gate_signals=gates,
        critical=critical,
        diligence_type=diligence,
    )


def resolve_claim_type(
    proposed: ClaimType,
    gates: list[GateId],
    forced: ClaimType | None,
    allow_study_fact: bool = False,
) -> ClaimType:
    """Code, not the model, decides which column of the evidence-weight table applies.

    The model's choice would let it move confidence: a registry record weighs 0 for efficacy
    claims but 1.0 for facts about studies, so an efficacy claim labelled `other` would borrow
    that weight. A module fixes its type; otherwise a claim that asserts a kill criterion is
    `target_causal` for K3 (a genetics claim) and `study_fact` for the rest (a trial was stopped,
    a competitor is in Phase 3, a sponsor dropped the program: facts about studies and
    programs, which is what a registry establishes); anything else keeps the model's label, except
    that `study_fact` (the only type a registry record can fully support) is allowed only in the
    modules that describe studies and programs.
    """
    if forced is not None:
        return forced
    if gates:
        return ClaimType.TARGET_CAUSAL if set(gates) == {GateId.K3} else ClaimType.STUDY_FACT
    if proposed is ClaimType.STUDY_FACT and not allow_study_fact:
        return ClaimType.DRUG_ACTS_IN_HUMANS
    return proposed


MAX_CRITICAL = 4


def cap_critical(claims: list[Claim], limit: int = MAX_CRITICAL) -> tuple[list[Claim], list[Drop]]:
    """Keep `critical` on at most `limit` claims, the first ones in the order the modules wrote them.

    The verdict hinges on critical claims (every one must reach the confidence bar to allow
    Invest), so the model cannot be left to decide how many there are.
    """
    kept, drops, count = [], [], 0
    for claim in claims:
        if claim.critical:
            count += 1
            if count > limit:
                drops.append(
                    Drop(
                        claim.id,
                        "critical",
                        f"more than {limit} critical claims",
                        DropKind.CRITICAL,
                    )
                )
                claim = claim.model_copy(update={"critical": False})
        kept.append(claim)
    return kept, drops


def fill_missing_chain_links(
    claims: list[Claim], bundle: Bundle, run_id: str, first_number: int
) -> list[Claim]:
    """One `unknown` claim for every chain link no claim speaks to: missing links are explicit."""
    covered = {c.chain_link for c in claims if c.chain_link is not None}
    added, number = [], first_number
    for link in ChainLink:
        if link in covered:
            continue
        added.append(
            Claim(
                id=f"C-{number:04d}",
                run_id=run_id,
                section=Section.TRANSLATION,
                text=f"Not shown in the available evidence: {CHAIN_TEXT[link]}.",
                claim_type=ClaimType.DRUG_ACTS_IN_HUMANS,
                basis=Basis.UNKNOWN,
                status=_unknown_status(bundle, TRANSLATION_SOURCES),
                confidence=0.0,
                chain_link=link,
                diligence_type=DEFAULT_DILIGENCE[link],
            )
        )
        number += 1
    return added
