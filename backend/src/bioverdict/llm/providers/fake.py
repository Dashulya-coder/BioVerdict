"""Scripted provider for tests and offline development (the plan's 429, timeout, bad JSON)."""

from __future__ import annotations

from collections.abc import Callable

from bioverdict.llm.types import ProviderRequest, ProviderResponse

Outcome = str | Exception | Callable[[ProviderRequest], ProviderResponse]


class FakeProvider:
    """Plays back `outcomes` in order, then repeats the last one.

    A `str` is a JSON answer, an `Exception` is raised, a callable builds the response itself.
    """

    def __init__(self, *outcomes: Outcome, name: str = "fake", tokens: tuple[int, int] = (100, 50)):
        if not outcomes:
            raise ValueError("FakeProvider needs at least one outcome")
        self.name = name
        self.requests: list[ProviderRequest] = []
        self._outcomes = list(outcomes)
        self._tokens = tokens

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        index = min(len(self.requests), len(self._outcomes)) - 1
        outcome = self._outcomes[index]
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome(request)
        return ProviderResponse(
            text=outcome,
            input_tokens=self._tokens[0],
            output_tokens=self._tokens[1],
            model=request.model,
        )
