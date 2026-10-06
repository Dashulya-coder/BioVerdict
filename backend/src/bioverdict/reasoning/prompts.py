"""Prompt text. The bundle is the whole world: nothing outside it may be used (closed world)."""

from __future__ import annotations

from bioverdict.store.models import Bundle, Evidence

CLOSED_WORLD = """\
You are one analyst on a biotech investment committee. You work only from the numbered evidence
below. Everything you know from elsewhere does not exist for this task: if the evidence does
not show it, it is unknown. The analysis date is {as_of}; ignore anything you may know that
happened later.

Rules for every claim:
- State one checkable fact or judgement in plain language.
- Support it with links. Each link names an evidence id exactly as listed and a quote copied
  character for character from that evidence's text. A quote that is not in the text is
  discarded together with your link.
- direction is "supports" or "contradicts" that claim; use "neutral" only if the evidence is
  merely related. Look for contradicting evidence actively and report it.
- basis "extracted": the claim is stated by a quote. "inferred": you conclude it from the
  evidence without a direct statement. "hypothesis": plausible but not supported. "unknown": the
  evidence does not say; give diligence_type, the kind of data that would answer it. Never fill
  a gap with a guess; an honest unknown is a result.
- Do not give numbers of your own (probabilities, market sizes, scores). Quote numbers that the
  evidence states.
- critical is true only for claims the investment decision hinges on (at most four).
"""


def render_evidence(evidence: list[Evidence]) -> str:
    blocks = []
    for e in sorted(evidence, key=lambda item: item.id):
        published = e.published_at.isoformat() if e.published_at else "undated"
        blocks.append(
            f"[{e.id}] {e.source} | kind={e.source_kind.value} | level={e.level.value} | "
            f"published={published} | group={e.independence_group}\n{e.excerpt}"
        )
    return "\n\n".join(blocks) if blocks else "(the bundle holds no evidence)"


def build_prompt(instruction: str, bundle: Bundle) -> str:
    statuses = ", ".join(f"{s.value}={v.value}" for s, v in sorted(bundle.section_statuses.items()))
    return (
        CLOSED_WORLD.format(as_of=bundle.as_of.isoformat())
        + f"\nSections searched so far: {statuses or 'none'}.\n\n"
        + f"## Your task\n{instruction}\n\n## Evidence\n{render_evidence(bundle.evidence)}\n"
    )
