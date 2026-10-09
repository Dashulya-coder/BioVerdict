"""Adapter for an OpenAI-compatible chat completions endpoint (the hackathon's Azure gateway).

What the gateway was observed to accept (probe of 2026-10-09, models gpt-6-luna, gpt-6.1-sol,
gpt-5-mini): chat completions only, `max_completion_tokens`, a system message, structured output
by `response_format` json_schema with strict mode, and `reasoning_effort`. It answers a 502 for
`temperature` and for the old `max_tokens`, and charges a reserved amount for that failed request,
so this adapter never sends them. Responses API, tools-free web search and several choices are not
available.
"""

from __future__ import annotations

import os
from typing import Any

import openai
from pydantic import ValidationError

from bioverdict.llm.errors import (
    FatalProviderError,
    InvalidOutputError,
    RefusalError,
    TransientProviderError,
)
from bioverdict.llm.types import ProviderRequest, ProviderResponse

SCHEMA_NAME = "answer"
REASONING_EFFORTS = {"low", "medium", "high"}
KEY_VARIABLES = ("TEAM_API_KEY", "OPENAI_API_KEY")  # the first one set is used
BASE_URL_VARIABLE = "LLM_BASE_URL"


def configured_key() -> str | None:
    return next((os.environ[v] for v in KEY_VARIABLES if os.environ.get(v)), None)


def classify_error(exc: Exception) -> Exception:
    """Map an SDK exception to the layer's classified errors (most specific class first)."""
    if isinstance(exc, openai.APITimeoutError):
        return TransientProviderError(str(exc), "timeout")
    if isinstance(exc, openai.APIConnectionError):
        return TransientProviderError(str(exc), "server")
    if isinstance(exc, openai.RateLimitError):
        return TransientProviderError(str(exc), "rate_limit")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return TransientProviderError(str(exc), "quota")
        if exc.status_code >= 500:  # includes the gateway's 502 upstream_error
            return TransientProviderError(str(exc), "server")
        return FatalProviderError(f"{exc.status_code} {exc.message}")
    return exc


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        client: Any = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        max_retries: int = 1,
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._api_key = api_key
        self._max_retries = max_retries

    def _sdk(self) -> Any:
        if self._client is None:
            self._client = openai.OpenAI(
                base_url=self._base_url or os.environ.get(BASE_URL_VARIABLE) or None,
                api_key=self._api_key or configured_key(),
                max_retries=self._max_retries,
            )
        return self._client

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """One structured answer. The reply is read here, so that the tokens of an answer that
        turns out unusable (cut off, refused, not JSON) are still known and charged."""
        # openai's own strict-schema form of the Pydantic model (all fields required, no extras)
        schema = openai.pydantic_function_tool(request.schema, name=SCHEMA_NAME)["function"][
            "parameters"
        ]
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": SCHEMA_NAME, "schema": schema, "strict": True},
            },
            "timeout": request.timeout_s,
        }
        if request.effort in REASONING_EFFORTS:
            kwargs["reasoning_effort"] = request.effort
        # `temperature` is deliberately never sent: see the module docstring.

        try:
            response = self._sdk().chat.completions.create(**kwargs)
        except openai.APIError as exc:
            raise classify_error(exc) from exc

        usage = getattr(response, "usage", None)  # completion tokens include reasoning tokens
        tokens = (
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )
        choice = response.choices[0]
        message = choice.message
        if getattr(message, "refusal", None) or choice.finish_reason == "content_filter":
            reason = getattr(message, "refusal", None) or "content filter"
            raise RefusalError(f"{request.model} declined the request ({reason})").with_usage(
                *tokens
            )
        if choice.finish_reason == "length":
            raise FatalProviderError(
                f"answer cut off at max_completion_tokens={request.max_tokens}; "
                "raise it for this step (reasoning tokens count too)"
            ).with_usage(*tokens)
        text = getattr(message, "content", None)
        if not text:
            raise InvalidOutputError("the response held no text").with_usage(*tokens)
        try:
            parsed = request.schema.model_validate_json(text)
        except ValidationError as exc:
            raise InvalidOutputError(str(exc)).with_usage(*tokens) from exc
        return ProviderResponse(
            text=parsed.model_dump_json(),
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            model=getattr(response, "model", request.model),
        )
