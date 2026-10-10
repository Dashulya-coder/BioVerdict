"""The four modules read the same bundle, so their model calls run together."""

import threading
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from bioverdict.llm import FakeLLM, TransientProviderError
from bioverdict.reasoning import ALL_MODULES, ModuleReasoner
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.store.models import Bundle, LLMResult

BUNDLE = Bundle.model_validate_json(
    (Path(__file__).parents[3] / "fixtures/bundles/divarasib.json").read_text()
)
ANSWER = {"claims": [{"text": "x", "claim_type": "other", "basis": "unknown", "links": []}]}


class SlowLLM:
    """Every call takes `delay` seconds; remembers how many calls overlapped."""

    def __init__(self, delay: float = 0.2, fail_step: str | None = None) -> None:
        self.delay, self.fail_step = delay, fail_step
        self._active = self.peak = 0
        self._lock = threading.Lock()

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            time.sleep(self.delay)
            if step == self.fail_step:
                raise TransientProviderError("boom", "server")
            # a different claim per step, so that the order of the ids can be checked
            answer = {"claims": [{**ANSWER["claims"][0], "text": f"claim of {step}"}]}
            return LLMResult(step=step, provider="fake", model="fake", parsed=answer)
        finally:
            with self._lock:
                self._active -= 1


def test_the_four_calls_overlap_in_time() -> None:
    llm = SlowLLM(delay=0.3)
    started = time.perf_counter()
    ModuleReasoner(llm, "R-1").reason(BUNDLE)
    elapsed = time.perf_counter() - started
    assert llm.peak == len(ALL_MODULES)
    assert elapsed < 0.3 * len(ALL_MODULES) * 0.75  # well under the sum of the four calls


def test_max_parallel_one_runs_the_calls_one_after_another() -> None:
    llm = SlowLLM(delay=0.05)
    ModuleReasoner(llm, "R-1", max_parallel=1).reason(BUNDLE)
    assert llm.peak == 1


def test_claim_ids_and_order_do_not_depend_on_which_call_finishes_first() -> None:
    parallel = ModuleReasoner(SlowLLM(delay=0.02), "R-1").reason(BUNDLE)
    serial = ModuleReasoner(SlowLLM(delay=0.02), "R-1", max_parallel=1).reason(BUNDLE)
    assert parallel == serial
    texts = [c.text for c in parallel[0] if c.text.startswith("claim of")]
    assert texts == [f"claim of {m.step}" for m in ALL_MODULES]  # module order, ids C-0001...
    assert [c.id for c in parallel[0]][: len(ALL_MODULES)] == [f"C-000{i}" for i in range(1, 7)]


def test_a_failing_module_fails_the_reasoning_with_its_own_error() -> None:
    llm = SlowLLM(delay=0.02, fail_step="reasoning.clinical")
    with pytest.raises(TransientProviderError):
        ModuleReasoner(llm, "R-1").reason(BUNDLE)


def test_canned_answers_still_work() -> None:
    empty = ModuleDraft(claims=[])
    llm = FakeLLM({m.step: empty for m in ALL_MODULES})
    claims, _ = ModuleReasoner(llm, "R-1").reason(BUNDLE)
    assert claims  # the missing chain links, as unknown claims
