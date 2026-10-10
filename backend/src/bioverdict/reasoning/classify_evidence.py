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
from bioverdict.llm.sizing import wire_len
from bioverdict.reasoning.grounding import (
    MIN_QUOTE_CHARS,
    TRANSLATION_SOURCES,
    Drop,
    DropKind,
    Grounded,
    ground_draft,
)
from bioverdict.reasoning.modules import CLINICAL, TRANSLATION
from bioverdict.reasoning.prompts import (
    CLOSED_WORLD,
    DEFAULT_EXCERPT_CAP,
    RETRY_RESERVE,
    boundary_tag,
    render_evidence,
)
from bioverdict.reasoning.schemas import DraftClaim, ModuleDraft
from bioverdict.store.models import (
    Basis,
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
   (for example a trial stopped for futility, or a safety action), and only about the asset or
   class this report is about, in the disease it is about. Same rules as for any claim: a verbatim
   quote, a basis, no numbers of your own. Leave the list empty when the existing claims already
   cover the evidence.
   The report holds `unknown` claims for links of the translation chain that no evidence showed
   (the third word in brackets names the link). If the new evidence shows such a link, state what
   it shows as a new claim with `chain_link` set to that link and a basis other than `unknown`;
   do not link the evidence to the `unknown` claim. Code retires the `unknown` claim and decides
   how far the new one reaches. Set `chain_link` only for a link of the chain (molecular_effect,
   human_exposure, target_engagement, biological_response, patient_benefit), never for a fact
   that asserts a kill criterion.
3. unmatched: ids of new evidence that bears on nothing in the report. Evidence about another drug
   or another disease belongs here, even if it is a strong result: it is not a link and not a
   new claim.

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
    rejected_claims: set[str] = field(default_factory=set)
    unread: list[str] = field(default_factory=list)  # new evidence no batch had room for
    llm_results: list[LLMResult] = field(default_factory=list)
    # `unknown` claims of a chain link that a new claim now shows: old claim id -> new claim id.
    # The caller drops the old claim, so the report does not say "not shown" beside the claim
    # that shows it.
    gaps_closed: dict[str, str] = field(default_factory=dict)


MAX_CLAIM_CHARS = 240  # an existing claim is shown by its beginning in the prompt
MAX_BATCHES = 6


MIN_CLAIM_CHARS = 60  # a claim is never shown by less than this when the prompt is crowded
EVIDENCE_ROOM = 2_000  # what a prompt keeps for the new evidence, however many claims there are
LINE_OVERHEAD = 70  # "[C-0007] (clinical, extracted, human_exposure) " and the newline


def _existing(claims: list[Claim], cap: int = MAX_CLAIM_CHARS) -> str:
    return "\n".join(
        f"[{c.id}] ({c.section.value}, {c.basis.value}"
        f"{', ' + c.chain_link.value if c.chain_link else ''}) {c.text[:cap]}"
        for c in sorted(claims, key=lambda c: c.id)
    )


def claim_cap(claims: list[Claim], budget: int | None, bundle: Bundle) -> int:
    """How much of each claim the prompt shows. A report of dozens of claims would otherwise leave
    no room for the new evidence on a small endpoint (a live run of 61 claims turned the added
    document away as "not read"): the claims are shortened, down to `MIN_CLAIM_CHARS`, before the
    evidence is."""
    if budget is None or not claims:
        return MAX_CLAIM_CHARS
    room = budget - wire_len(_assemble([], "", bundle)) - RETRY_RESERVE - EVIDENCE_ROOM
    each = room // len(claims) - LINE_OVERHEAD
    return max(MIN_CLAIM_CHARS, min(MAX_CLAIM_CHARS, each))


def _assemble(
    claims: list[Claim], evidence: str, bundle: Bundle, cap: int = MAX_CLAIM_CHARS
) -> str:
    return (
        CLOSED_WORLD.format(as_of=bundle.as_of.isoformat(), tag=boundary_tag(bundle))
        + f"\n## Your task\n{_TASK}\n## Existing claims\n{_existing(claims, cap) or '(none)'}\n"
        + f"\n## New evidence\n{evidence}\n"
    )


def build_prompt(claims: list[Claim], new_evidence: list[Evidence], bundle: Bundle) -> str:
    evidence, _ = render_evidence(new_evidence, boundary_tag(bundle))
    return _assemble(claims, evidence, bundle)


def build_prompts(
    claims: list[Claim], new_evidence: list[Evidence], bundle: Bundle, budget: int | None
) -> tuple[list[tuple[str, list[Evidence]]], list[str]]:
    """The prompts that carry `new_evidence` and, for each, the evidence it shows.

    Every prompt lists all existing claims (so each piece of evidence can be placed) and as much
    of the new evidence as the budget leaves room for; the rest goes to the next prompt, up to
    MAX_BATCHES. Returns the prompts and the ids that no prompt had room for.
    """
    if budget is None:
        return [(build_prompt(claims, new_evidence, bundle), new_evidence)], []
    tag = boundary_tag(bundle)
    cap = claim_cap(claims, budget, bundle)
    room = max(0, budget - wire_len(_assemble(claims, "", bundle, cap)) - RETRY_RESERVE)
    prompts: list[tuple[str, list[Evidence]]] = []
    remaining = new_evidence
    while remaining and len(prompts) < MAX_BATCHES:
        text, omitted = render_evidence(remaining, tag, room, DEFAULT_EXCERPT_CAP)
        left = set(omitted)
        shown = [e for e in remaining if e.id not in left]
        if not shown:  # not even one piece fits beside the claims
            break
        prompts.append((_assemble(claims, text, bundle, cap), shown))
        remaining = [e for e in remaining if e.id in left]
    return prompts, [e.id for e in remaining]


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
    if not new_evidence:  # a control recompute adds nothing: there is nothing to ask the model
        return result
    budget_of = getattr(llm, "input_budget", None)
    budget = budget_of(STEP, Classification) if callable(budget_of) else None
    prompts, result.unread = build_prompts(claims, new_evidence, bundle, budget)
    answers = [llm.call(STEP, text, Classification) for text, _ in prompts]
    result.llm_results = answers
    parsed = Classification(
        links=[l for a in answers for l in Classification.model_validate(a.parsed).links],
        new_claims=[c for a in answers for c in Classification.model_validate(a.parsed).new_claims],
        unmatched=[u for a in answers for u in Classification.model_validate(a.parsed).unmatched],
    )

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

    # A new fact that shows a link of the translation chain is grounded like a claim of the
    # translation module (its section, its claim type, the chain link kept), so it can speak for
    # that link. A claim that also asserts a kill criterion stays clinical: the translation module
    # asserts no gate, and the chain link the model put on it is then dropped and logged.
    # Every other new fact is grounded like a claim of the clinical module (the one that describes
    # studies and programs): its gate tags are checked against the evidence, and study_fact is
    # allowed.
    on_chain = [c for c in parsed.new_claims if c.chain_link is not None and not c.gate_signals]
    elsewhere = [c for c in parsed.new_claims if c.chain_link is None or c.gate_signals]
    next_number = max((int(c.id.removeprefix("C-")) for c in claims), default=0) + 1
    chain = ground_draft(
        ModuleDraft(claims=on_chain),
        bundle,
        run_id,
        TRANSLATION.section,
        allow_chain=True,
        evidence_sections=TRANSLATION_SOURCES,
        forced_type=TRANSLATION.claim_type,
        first_number=next_number,
    )
    rest = ground_draft(
        ModuleDraft(claims=elsewhere),
        bundle,
        run_id,
        CLINICAL.section,
        allowed_gates=CLINICAL.allowed_gates,
        gate_guard=CLINICAL.gate_guard,
        allow_study_fact=CLINICAL.allow_study_fact,
        first_number=next_number + len(chain.claims),
    )
    grounded = Grounded(
        claims=[*chain.claims, *rest.claims],
        links=[*chain.links, *rest.links],
        drops=[*chain.drops, *rest.drops],
    )
    # Apply the same fail-closed citation rule as the first reasoning pass: one invented
    # citation rejects the entire new claim, even if another citation was grounded.
    rejected = {d.claim_id for d in grounded.drops if d.is_citation_failure}
    cited = {link.claim_id for link in grounded.links}
    rejected |= {
        c.id for c in grounded.claims if c.basis is not Basis.UNKNOWN and c.id not in cited
    }
    result.rejected_claims = rejected
    result.new_claims = [c for c in grounded.claims if c.id not in rejected]
    result.new_claim_links = [l for l in grounded.links if l.claim_id not in rejected]
    result.drops += grounded.drops
    result.unmatched = [i for i in parsed.unmatched if i in new_by_id]
    # A gap is closed by a claim that survived grounding on a link of the chain and is not itself
    # a gap. How far the link then reaches is the formula's business, not decided here.
    for new in result.new_claims:
        if new.chain_link is None or new.basis is Basis.UNKNOWN:
            continue
        for old in claims:
            if old.basis is Basis.UNKNOWN and old.chain_link is new.chain_link:
                result.gaps_closed.setdefault(old.id, new.id)
    return result
