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

from bioverdict.reasoning.schemas import DraftClaim, ModuleDraft
from bioverdict.store.models import (
    Basis,
    Bundle,
    ChainLink,
    Claim,
    ClaimEvidenceLink,
    DiligenceType,
    GateId,
    Section,
    SectionStatus,
)

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


@dataclass(frozen=True)
class Drop:
    """Something the model proposed and code removed, with the reason (feeds verification_log)."""

    claim_id: str
    what: str
    reason: str


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
    first_number: int = 1,
) -> Grounded:
    out = Grounded()
    evidence = bundle.evidence_by_id()
    number = first_number

    for item in draft.claims:
        if not item.text.strip():
            out.drops.append(Drop("-", "claim", "empty text"))
            continue
        claim_id = f"C-{number:04d}"
        number += 1

        links, seen = [], set()
        for link in item.links:
            ev = evidence.get(link.evidence_id)
            if ev is None:
                out.drops.append(Drop(claim_id, link.evidence_id, "evidence is not in the bundle"))
            elif link.quote not in ev.excerpt:
                out.drops.append(Drop(claim_id, link.evidence_id, "quote is not in the excerpt"))
            elif link.evidence_id in seen:
                out.drops.append(Drop(claim_id, link.evidence_id, "evidence cited twice"))
            else:
                seen.add(link.evidence_id)
                links.append(
                    ClaimEvidenceLink(
                        claim_id=claim_id,
                        evidence_id=link.evidence_id,
                        direction=link.direction,
                        quote=link.quote,
                    )
                )

        out.claims.append(
            _build_claim(
                item,
                claim_id,
                run_id,
                section,
                bool(links),
                bundle,
                out,
                allowed_gates,
                allow_chain,
                evidence_sections or (section,),
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
) -> Claim:
    gates = [g for g in item.gate_signals if g in allowed_gates]
    for g in item.gate_signals:
        if g not in allowed_gates:
            out.drops.append(Drop(claim_id, g.value, "gate is outside this module's remit"))

    chain_link = item.chain_link if allow_chain else None
    if item.chain_link is not None and not allow_chain:
        out.drops.append(Drop(claim_id, item.chain_link.value, "chain link outside translation"))

    basis, diligence, status = Basis(item.basis), item.diligence_type, SectionStatus.FOUND
    if basis is Basis.EXTRACTED and not has_links:
        basis = Basis.INFERRED
        out.drops.append(
            Drop(claim_id, "basis", "extracted without a grounded quote: now inferred")
        )
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
        claim_type=item.claim_type,
        basis=basis,
        status=status,
        confidence=0.0,  # computed from the evidence by scoring.apply_confidence
        chain_link=chain_link,
        gate_signals=gates,
        critical=item.critical,
        diligence_type=diligence,
    )


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
                basis=Basis.UNKNOWN,
                status=_unknown_status(bundle, TRANSLATION_SOURCES),
                confidence=0.0,
                chain_link=link,
                diligence_type=DEFAULT_DILIGENCE[link],
            )
        )
        number += 1
    return added
