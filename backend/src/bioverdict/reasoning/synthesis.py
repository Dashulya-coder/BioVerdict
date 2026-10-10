"""The synthesis step: the written theses of the underwriting report.

The modules wrote claims and code computed the verdict, the module answers and the figures. The
brief also asks for prose a reader expects: a scientific and a human translation thesis, a plan
for the next trial, the competitive landscape, the commercial opportunity and the investment case
(value inflection points, financing, licensing or acquisition). A model writes them over the
claims only, after the Chair, and the report labels them as inference.

Code keeps a sentence only if it cites claims of the run, and only if every number in it appears
in a claim it cites or in the figures code gave it: the model cannot bring in a number of its own.
Like the Skeptic and the Chair the step is advisory: the verdict does not depend on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import Field

from bioverdict.contracts import LLM
from bioverdict.llm.sizing import wire_len
from bioverdict.reasoning.critique import _claim_lines, _fit, _left_out, _preamble
from bioverdict.reasoning.prompts import RETRY_RESERVE
from bioverdict.reasoning.schemas import _Draft
from bioverdict.scoring.verdict import GATE_TEXT
from bioverdict.store.models import (
    Basis,
    Bundle,
    Claim,
    Range,
    Thesis,
    ThesisKind,
    ThesisSentence,
    VerdictResult,
)

SYNTHESIS_STEP = "synthesis"
MAX_SENTENCES = 4  # of one thesis: the report is read, not searched


class DraftSentence(_Draft):
    text: str = Field(description="One sentence of at most 40 words, with no claim ids in it")
    claim_ids: list[str] = Field(description="The claims the sentence rests on, e.g. C-0003")


class DraftThesis(_Draft):
    kind: ThesisKind
    sentences: list[DraftSentence]


class SynthesisDraft(_Draft):
    theses: list[DraftThesis]


_SYNTHESIS = """\
You write the theses of the committee's report for a reader who will not read every claim. The
claims below are what the evidence supports, with the confidence the scoring formula gave each;
the figures were computed by code. Write each part in at most 4 sentences:
- scientific: is the target causal for the disease, or only correlated with it; what is causal
  evidence (human genetics, perturbation, an effective prior drug) and what is only association;
  what contradicts it.
- translation: the chain molecular effect, human exposure, target engagement, biological
  response, patient benefit: which links the claims show, which are weak, which are missing.
- development_plan: the next trial the program needs: the patient population, the endpoint, the
  biomarker strategy, the comparator, the approximate size and the sequence of trials. Take each
  from the trials in the claims and say which similar programs succeeded or failed and what that
  implies. Give a size only as a trial in the claims enrolled it.
- competitive: approved therapies, competitors ahead, other programs on the same target, other
  mechanisms, discontinued programs, and the differentiation a new entrant would need.
- commercial: who would be treated and what treats them today, as far as the claims say;
  whether the program is commercially valuable or only scientifically interesting, and why.
- investment: the capital and time to the next milestone (figures below), the value inflection
  points (readouts, filings, approvals the claims name), later financing, and the plausible
  outcomes (licensing, acquisition, own development) with what each would depend on.
Rules:
- Every sentence cites at least one claim id from the list. Do not write ids in the sentence.
- Numbers: copy only numbers that a claim you cite or the figures state, written the same way. A
  sentence with any other number is discarded. Give no probability, price or size of your own.
- State nothing that no cited claim states. Where the claims say a thing is unknown, say it is
  unknown; do not fill the gap. This is a synthesis of the claims, not new evidence.
"""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Not figures: a claim id, and the phase of a trial (Phase 1 to 4, also as "Phase 2/3").
_NOT_A_FIGURE = re.compile(r"\bC-\d+\b|\b[Pp]hase\s*[1-4](?:\s*/\s*[1-4])?\b")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(_NOT_A_FIGURE.sub(" ", text))}


def _usd(value: float) -> str:
    return f"${value / 1e6:,.0f} million"


def _range(r: Range, fmt) -> str:
    return f"{fmt(r.p50)} (P10 {fmt(r.p10)}, P90 {fmt(r.p90)})"


def figures(result: VerdictResult, module_lines: list[str], missing: list[str]) -> str:
    """What code computed, written as the model may quote it."""
    lines = [f"- Verdict: {result.verdict.value} (confidence {result.confidence:.2f})"]
    fired = [g for g in result.gates if g.fired]
    if fired:
        lines += [f"- Gate {g.gate_id.value} fired: {GATE_TEXT[g.gate_id]}" for g in fired]
    lines += [f"- Module answer: {line}" for line in module_lines]
    if result.pos:
        lines.append(f"- Probability of success: {_range(result.pos, lambda v: f'{v * 100:.0f}%')}")
    if result.capital_to_milestone:
        lines.append(
            f"- Capital to the next milestone: {_range(result.capital_to_milestone, _usd)}"
        )
    if result.months_to_milestone:
        lines.append(
            "- Time to the next milestone: "
            f"{_range(result.months_to_milestone, lambda v: f'{v:.0f} months')}"
        )
    if result.capital:
        lines.append(f"- Capital to approval: {_range(result.capital, _usd)}")
    if result.rnpv:
        lines.append(f"- rNPV: {_range(result.rnpv, _usd)}")
    lines += [f"- Not computed: {why}" for why in missing]
    lines.append(
        "- The capital, time and rNPV figures rest on placeholder phase costs and durations, not "
        "on benchmarks: say so when you use them."
    )
    return "\n".join(lines)


def _order(claim: Claim) -> tuple[bool, bool, bool, float, str]:
    """Key claims, claims behind gates and flags, then the most confident; gaps last."""
    return (
        not claim.critical,
        not (claim.gate_signals or claim.flags),
        claim.basis is Basis.UNKNOWN,
        -claim.confidence,
        claim.id,
    )


def synthesis_prompt(bundle: Bundle, claims: list[Claim], facts: str, budget: int | None) -> str:
    head = (
        f"{_preamble(bundle)}\n## Your task\n{_SYNTHESIS}\n## Figures computed by code\n{facts}\n"
    )
    shown, hidden = claims, 0
    if budget is not None:
        room = max(0, budget - wire_len(head) - RETRY_RESERVE - 80)
        shown, hidden = _fit(sorted(claims, key=_order), room)
    return f"{head}\n## Claims\n{_claim_lines(shown)}{_left_out(hidden)}\n"


@dataclass
class SynthesisResult:
    theses: list[Thesis] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # why each discarded sentence went


def ground(draft: SynthesisDraft, claims: list[Claim], facts: str) -> SynthesisResult:
    """The sentences code can stand behind, in report order; the rest with the reason."""
    by_id = {c.id: c for c in claims}
    allowed = _numbers(facts)
    out = SynthesisResult()
    seen: set[ThesisKind] = set()
    kept: dict[ThesisKind, list[ThesisSentence]] = {}
    for thesis in draft.theses:
        if thesis.kind in seen:
            out.dropped.append(f"{thesis.kind.value}: written twice, the second dropped")
            continue
        seen.add(thesis.kind)
        for sentence in thesis.sentences:
            text = " ".join(sentence.text.split())
            ids = list(dict.fromkeys(i for i in sentence.claim_ids if i in by_id))
            if not text:
                continue
            if not ids:
                out.dropped.append(f"{thesis.kind.value}: cites no claim of the run: {text}")
                continue
            sources = allowed | set().union(*(_numbers(by_id[i].text) for i in ids))
            foreign = sorted(_numbers(text) - sources)
            if foreign:
                out.dropped.append(
                    f"{thesis.kind.value}: number(s) {', '.join(foreign)} in no cited claim "
                    f"and no figure: {text}"
                )
                continue
            if len(kept.setdefault(thesis.kind, [])) < MAX_SENTENCES:
                kept[thesis.kind].append(ThesisSentence(text=text, claim_ids=ids))
    out.theses = [Thesis(kind=kind, sentences=kept[kind]) for kind in ThesisKind if kept.get(kind)]
    return out


def write_theses(
    llm: LLM,
    bundle: Bundle,
    claims: list[Claim],
    result: VerdictResult,
    module_lines: list[str],
    missing: list[str],
) -> SynthesisResult:
    """The theses of the report, each sentence grounded in claims and figures by code."""
    facts = figures(result, module_lines, missing)
    budget_of = getattr(llm, "input_budget", None)
    budget = budget_of(SYNTHESIS_STEP, SynthesisDraft) if callable(budget_of) else None
    answer = llm.call(
        SYNTHESIS_STEP, synthesis_prompt(bundle, claims, facts, budget), SynthesisDraft
    )
    return ground(SynthesisDraft.model_validate(answer.parsed), claims, facts)
