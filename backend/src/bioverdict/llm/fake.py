"""`FakeLLM`: canned answers per step, so either track can run the whole DAG offline."""

from __future__ import annotations

from pydantic import BaseModel

from bioverdict.store.models import LLMResult


class FakeLLM:
    """Satisfies the `LLM` contract. `answers` maps a step name to a model instance or a dict."""

    def __init__(self, answers: dict[str, BaseModel | dict]) -> None:
        self._answers = answers
        self.calls: list[tuple[str, str]] = []

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        self.calls.append((step, prompt))
        if step not in self._answers:
            raise KeyError(f"FakeLLM has no canned answer for step {step!r}")
        raw = self._answers[step]
        data = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        parsed = schema.model_validate(data).model_dump(mode="json")  # must fit the schema
        return LLMResult(step=step, provider="fake", model="fake", parsed=parsed)
