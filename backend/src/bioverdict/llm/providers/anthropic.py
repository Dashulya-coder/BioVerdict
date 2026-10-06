"""Anthropic adapter (Claude API, Messages API with structured outputs).

Model-specific rules (Claude API reference, checked 2026-10-07):
- `claude-sonnet-5-*`, `claude-opus-5-*`, `claude-fable-*` reject non-default `temperature`; they
  are deterministic only through the response cache and a pinned model id, not temperature 0.
- `claude-haiku-*` has no `effort` parameter and still takes `temperature`.
- Thinking is left at the model default (adaptive on the 5.x models).
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import ValidationError

from bioverdict.llm.errors import (
    FatalProviderError,
    InvalidOutputError,
    RefusalError,
    TransientProviderError,
)
from bioverdict.llm.types import ProviderRequest, ProviderResponse

_REJECTS_SAMPLING = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-fable",
    "claude-mythos",
)


def accepts_sampling(model: str) -> bool:
    return not model.startswith(_REJECTS_SAMPLING)


def supports_effort(model: str) -> bool:
    return not model.startswith("claude-haiku")


def classify_error(exc: Exception) -> Exception:
    """Map an SDK exception to the layer's classified errors (most specific class first)."""
    if isinstance(exc, anthropic.APITimeoutError):
        return TransientProviderError(str(exc), "timeout")
    if isinstance(exc, anthropic.APIConnectionError):
        return TransientProviderError(str(exc), "server")
    if isinstance(exc, anthropic.RateLimitError):
        return TransientProviderError(str(exc), "rate_limit")
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code == 402:
            return TransientProviderError(str(exc), "quota")
        if exc.status_code >= 500:  # includes 529 overloaded
            return TransientProviderError(str(exc), "server")
        return FatalProviderError(f"{exc.status_code} {exc.message}")
    return exc


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any = None, max_retries: int = 1) -> None:
        self._client = client
        self._max_retries = max_retries  # SDK-level retries for blips; failover handles the rest

    def _sdk(self) -> Any:
        if self._client is None:
            self._client = anthropic.Anthropic(max_retries=self._max_retries)
        return self._client

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
            "output_format": request.schema,
            "timeout": request.timeout_s,
        }
        if request.system:
            kwargs["system"] = request.system
        if request.effort and supports_effort(request.model):
            kwargs["output_config"] = {"effort": request.effort}
        if request.temperature is not None and accepts_sampling(request.model):
            kwargs["temperature"] = request.temperature

        try:
            response = self._sdk().messages.parse(**kwargs)
        except ValidationError as exc:
            raise InvalidOutputError(str(exc)) from exc
        except anthropic.APIError as exc:
            classified = classify_error(exc)
            raise classified from exc

        if response.stop_reason == "refusal":
            raise RefusalError(f"{request.model} declined the request")
        if response.stop_reason == "max_tokens":
            raise FatalProviderError(
                f"answer cut off at max_tokens={request.max_tokens}; raise it for this step"
            )
        parsed = response.parsed_output
        if parsed is None:
            raise InvalidOutputError("the response held no parsable JSON")
        return ProviderResponse(
            text=parsed.model_dump_json(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=getattr(response, "model", request.model),
        )
