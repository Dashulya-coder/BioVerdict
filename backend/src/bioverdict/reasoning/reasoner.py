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
from bioverdict.reasoning.prompts import (
    MAX_EVIDENCE_CHARS,
    BuiltPrompt,
    build_prompt,
    build_prompts,
)
from bioverdict.reasoning.schemas import ModuleDraft, merge_drafts
from bioverdict.scoring.confidence import apply_confidence
from bioverdict.scoring.config import ConfidenceConfig
from bioverdict.store.models import Bundle, Claim, ClaimEvidenceLink, LLMResult, Section

_TRANSLATION_SOURCES = (Section.CLINICAL, Section.MECHANISM)
MAX_WORKERS = 6  # simultaneous model calls: a gateway has its own rate limits


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
        max_batches: int = 3,
    ) -> None:
        self._llm = llm
        self._run_id = run_id
        self._modules = modules
        self._confidence = confidence
        self._max_evidence_chars = max_evidence_chars
        self._max_parallel = max_parallel  # None: all calls at once (up to 6); 1: one at a time
        self._max_batches = max_batches  # batches of evidence per module when it does not fit one
        self.trace = ReasoningTrace()

    def _prompts(self, module: ReasoningModule, bundle: Bundle) -> list[BuiltPrompt]:
        """The prompts of the module: one, or several batches when the endpoint takes less than
        the evidence (input_budget), so that all the evidence is read."""
        budget_of = getattr(self._llm, "input_budget", None)
        budget = budget_of(module.step, ModuleDraft) if callable(budget_of) else None
        if budget is None:
            return [
                build_prompt(
                    module.instruction,
                    bundle,
                    self._max_evidence_chars,
                    families=module.families,
                )
            ]
        return build_prompts(
            module.instruction,
            bundle,
            budget=budget,
            families=module.families,
            max_batches=self._max_batches,
        )

    def _workers(self, calls: int) -> int:
        return max(1, min(self._max_parallel or min(calls, MAX_WORKERS), calls))

    def reason(self, bundle: Bundle) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
        claims: list[Claim] = []
        links: list[ClaimEvidenceLink] = []
        self.trace = ReasoningTrace()

        # The modules read the bundle and nothing else, so their model calls are independent: they
        # run together (a run has a wall-clock limit and a call is a minute or two). Grounding and
        # numbering then follow the order of the modules, so the claim ids do not depend on which
        # call finished first.
        prompts = [self._prompts(m, bundle) for m in self._modules]
        for module_prompts in prompts:
            self.trace.omitted_evidence += module_prompts[-1].omitted
        calls = [
            (module, prompt)
            for module, module_prompts in zip(self._modules, prompts, strict=True)
            for prompt in module_prompts
        ]
        with ThreadPoolExecutor(max_workers=self._workers(len(calls))) as pool:
            futures = [
                pool.submit(self._llm.call, module.step, prompt.text, ModuleDraft)
                for module, prompt in calls
            ]
            results = [future.result() for future in futures]  # the first failure, in order

        position = 0
        for module, module_prompts in zip(self._modules, prompts, strict=True):
            batch_results = results[position : position + len(module_prompts)]
            position += len(module_prompts)
            self.trace.llm_results += batch_results
            draft = merge_drafts(
                [ModuleDraft.model_validate(r.parsed) for r in batch_results],
                drop_unknown=len(batch_results) > 1,
            )
            grounded = ground_draft(
                draft,
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
