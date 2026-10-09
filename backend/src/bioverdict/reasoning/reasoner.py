"""`Reasoner` contract: run the modules over a frozen bundle and return scored, grounded claims."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from bioverdict.contracts import LLM
from bioverdict.reasoning.grounding import (
    Drop,
    cap_critical,
    fill_missing_chain_links,
    ground_draft,
)
from bioverdict.reasoning.modules import ALL_MODULES, ReasoningModule
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
    """Runs mechanism, clinical, competition, then translation. Confidence is computed from the grounded links."""

    def __init__(
        self,
        llm: LLM,
        run_id: str,
        modules: tuple[ReasoningModule, ...] = ALL_MODULES,
        confidence: ConfidenceConfig | None = None,
        max_evidence_chars: int = MAX_EVIDENCE_CHARS,
        max_parallel: int | None = None,
    ) -> None:
        self._llm = llm
        self._run_id = run_id
        self._modules = modules
        self._confidence = confidence
        self._max_evidence_chars = max_evidence_chars
        self._max_parallel = max_parallel  # None: one call per module at once; 1: one after another
        self.trace = ReasoningTrace()

    def _workers(self) -> int:
        return max(1, min(self._max_parallel or len(self._modules), len(self._modules)))

    def reason(self, bundle: Bundle) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
        claims: list[Claim] = []
        links: list[ClaimEvidenceLink] = []
        self.trace = ReasoningTrace()

        # The modules read the bundle and nothing else, so their model calls are independent: they
        # run together (a run has a wall-clock limit and a call is a minute or two). Grounding and
        # numbering then follow the order of the modules, so the claim ids do not depend on which
        # call finished first.
        prompts = [
            build_prompt(m.instruction, bundle, self._max_evidence_chars) for m in self._modules
        ]
        for prompt in prompts:
            self.trace.omitted_evidence += prompt.omitted
        with ThreadPoolExecutor(max_workers=self._workers()) as pool:
            futures = [
                pool.submit(self._llm.call, module.step, prompt.text, ModuleDraft)
                for module, prompt in zip(self._modules, prompts, strict=True)
            ]
            results = [future.result() for future in futures]  # the first failure, in module order

        for module, result in zip(self._modules, results, strict=True):
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
                gate_guard=module.gate_guard,
                allow_study_fact=module.allow_study_fact,
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
