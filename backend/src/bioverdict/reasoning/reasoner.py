"""`Reasoner` contract: run the modules over a frozen bundle and return scored, grounded claims."""

from __future__ import annotations

from dataclasses import dataclass, field

from bioverdict.contracts import LLM
from bioverdict.reasoning.grounding import (
    Drop,
    cap_critical,
    fill_missing_chain_links,
    ground_draft,
)
from bioverdict.reasoning.modules import MECHANISM, TRANSLATION, ReasoningModule
from bioverdict.reasoning.prompts import MAX_EVIDENCE_CHARS, build_prompt
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.scoring.confidence import apply_confidence
from bioverdict.scoring.config import ConfidenceConfig
from bioverdict.store.models import Bundle, Claim, ClaimEvidenceLink, LLMResult, Section

_TRANSLATION_SOURCES = (Section.CLINICAL, Section.MECHANISM)


@dataclass
class ReasoningTrace:
    """What the run did besides the claims: model calls and everything code removed."""

    llm_results: list[LLMResult] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)
    omitted_evidence: list[str] = field(default_factory=list)  # left out of a prompt for length


class ModuleReasoner:
    """Runs mechanism then translation. Confidence is computed from the grounded links."""

    def __init__(
        self,
        llm: LLM,
        run_id: str,
        modules: tuple[ReasoningModule, ...] = (MECHANISM, TRANSLATION),
        confidence: ConfidenceConfig | None = None,
        max_evidence_chars: int = MAX_EVIDENCE_CHARS,
    ) -> None:
        self._llm = llm
        self._run_id = run_id
        self._modules = modules
        self._confidence = confidence
        self._max_evidence_chars = max_evidence_chars
        self.trace = ReasoningTrace()

    def reason(self, bundle: Bundle) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
        claims: list[Claim] = []
        links: list[ClaimEvidenceLink] = []
        self.trace = ReasoningTrace()

        for module in self._modules:
            prompt = build_prompt(module.instruction, bundle, self._max_evidence_chars)
            self.trace.omitted_evidence += prompt.omitted
            result = self._llm.call(module.step, prompt.text, ModuleDraft)
            self.trace.llm_results.append(result)
            grounded = ground_draft(
                ModuleDraft.model_validate(result.parsed),
                bundle,
                self._run_id,
                module.section,
                allowed_gates=module.allowed_gates,
                allow_chain=module.chain,
                evidence_sections=_TRANSLATION_SOURCES if module.chain else None,
                forced_type=module.claim_type,
                first_number=len(claims) + 1,
            )
            claims += grounded.claims
            links += grounded.links
            self.trace.drops += grounded.drops

        if any(m.chain for m in self._modules):
            claims += fill_missing_chain_links(claims, bundle, self._run_id, len(claims) + 1)

        claims, capped = cap_critical(claims)
        self.trace.drops += capped

        scored = apply_confidence(
            claims, links, bundle.evidence_by_id(), bundle.as_of, self._confidence
        )
        return scored, links
