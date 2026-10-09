"""Incremental recompute (ADR-007, architecture section 8): classify new evidence, do not redo.

When a document is added, running every reasoning module again changes the wording of claims that
have nothing to do with it, and a diff then shows model noise instead of the effect of the
document. Here the model only says where the new evidence belongs: which existing claims it
supports or contradicts, and (rarely) which fact it states that no claim does. Code grounds every
quote, adds the links and recomputes the confidence of all claims with the scoring formula, so
exactly the claims the evidence touches move, and the verdict follows from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.contracts import LLM
from bioverdict.reasoning.grounding import MIN_QUOTE_CHARS, Drop, DropKind, ground_draft
from bioverdict.reasoning.modules import CLINICAL
from bioverdict.reasoning.prompts import CLOSED_WORLD, boundary_tag, render_evidence
from bioverdict.reasoning.schemas import DraftClaim, ModuleDraft
from bioverdict.store.models import (
    Bundle,
    Claim,
    ClaimEvidenceLink,
    Direction,
    Evidence,
    LLMResult,
)

STEP = "reasoning.classify"

_TASK = """\
New evidence has arrived for a report that is already written. Do not rewrite the report. Say only
where the new evidence belongs.

1. links: for each piece of new evidence, every EXISTING claim it bears on, with direction
   "supports" or "contradicts" and a quote copied character for character from that evidence.
   Link a claim only if the evidence is about the same fact; related background is not a link.
   A weak or indirect result (a cell experiment against a human finding) is still a link: how
   much it matters is decided by code, not by you.
2. new_claims: only for a fact the new evidence states that no existing claim already states
   (for example a trial stopped for futility, or a safety action). Same rules as for any claim: a
   verbatim quote, a basis, no numbers of your own. Leave the list empty when the existing claims
   already cover the evidence.
3. unmatched: ids of new evidence that bears on nothing in the report.

Never give a confidence, a probability or a verdict.
"""


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewLink(_Item):
    claim_id: str = Field(description="An id of an existing claim, for example C-0007")
    evidence_id: str = Field(description="An id of a piece of NEW evidence")
    direction: Direction
    quote: str = Field(description="Copied character for character from that evidence's text")


class Classification(_Item):
    links: list[NewLink] = Field(default_factory=list)
    new_claims: list[DraftClaim] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)


@dataclass
class ClassifyResult:
    links: list[ClaimEvidenceLink] = field(default_factory=list)  # onto existing claims
    new_claims: list[Claim] = field(default_factory=list)
    new_claim_links: list[ClaimEvidenceLink] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)  # new evidence that bears on nothing
    drops: list[Drop] = field(default_factory=list)
    llm_result: LLMResult | None = None


def build_prompt(claims: list[Claim], new_evidence: list[Evidence], bundle: Bundle) -> str:
    tag = boundary_tag(bundle)
    existing = "\n".join(
        f"[{c.id}] ({c.section.value}, {c.basis.value}) {c.text}"
        for c in sorted(claims, key=lambda c: c.id)
    )
    evidence, _ = render_evidence(new_evidence, tag)
    return (
        CLOSED_WORLD.format(as_of=bundle.as_of.isoformat(), tag=tag)
        + f"\n## Your task\n{_TASK}\n## Existing claims\n{existing or '(none)'}\n"
        + f"\n## New evidence\n{evidence}\n"
    )


def classify_new_evidence(
    llm: LLM,
    run_id: str,
    claims: list[Claim],
    existing_links: list[ClaimEvidenceLink],
    new_evidence: list[Evidence],
    bundle: Bundle,
) -> ClassifyResult:
    """Ground the model's classification of `new_evidence` against the claims of a finished run.

    `bundle` holds all evidence (old and new) as of the recompute. Nothing the model says is kept
    unless its ids exist and its quote is verbatim in the evidence it names.
    """
    result = ClassifyResult()
    answer = llm.call(STEP, build_prompt(claims, new_evidence, bundle), Classification)
    result.llm_result = answer
    parsed = Classification.model_validate(answer.parsed)

    claim_ids = {c.id for c in claims}
    new_by_id = {e.id: e for e in new_evidence}
    seen = {(link.claim_id, link.evidence_id) for link in existing_links}
    for link in parsed.links:
        evidence = new_by_id.get(link.evidence_id)
        quote = link.quote.strip()
        reason = None
        if link.claim_id not in claim_ids:
            reason = "no such claim"
        elif evidence is None:
            reason = "not a piece of the new evidence"
        elif not quote:
            reason = "empty quote"
        elif len(quote) < MIN_QUOTE_CHARS and quote != evidence.excerpt.strip():
            reason = f"quote shorter than {MIN_QUOTE_CHARS} characters"
        elif quote not in evidence.excerpt:
            reason = "quote is not in the excerpt"
        elif (link.claim_id, link.evidence_id) in seen:
            reason = "already linked"
        if reason is not None:
            kind = DropKind.DUPLICATE_LINK if reason == "already linked" else DropKind.LINK
            result.drops.append(Drop(link.claim_id, link.evidence_id, reason, kind))
            continue
        seen.add((link.claim_id, link.evidence_id))
        result.links.append(
            ClaimEvidenceLink(
                claim_id=link.claim_id,
                evidence_id=link.evidence_id,
                direction=link.direction,
                quote=quote,
            )
        )

    # A new fact is grounded like a claim of the clinical module (the one that describes studies
    # and programs): its gate tags are checked against the evidence, and study_fact is allowed.
    next_number = max((int(c.id.removeprefix("C-")) for c in claims), default=0) + 1
    grounded = ground_draft(
        ModuleDraft(claims=parsed.new_claims),
        bundle,
        run_id,
        CLINICAL.section,
        allowed_gates=CLINICAL.allowed_gates,
        gate_guard=CLINICAL.gate_guard,
        allow_study_fact=CLINICAL.allow_study_fact,
        first_number=next_number,
    )
    result.new_claims = grounded.claims
    result.new_claim_links = grounded.links
    result.drops += grounded.drops
    result.unmatched = [i for i in parsed.unmatched if i in new_by_id]
    return result
