from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from bioverdict.llm.errors import (
    FatalProviderError,
    InvalidOutputError,
    RefusalError,
    TransientProviderError,
)
from bioverdict.llm.providers.anthropic import (
    AnthropicProvider,
    accepts_sampling,
    classify_error,
    supports_effort,
)
from bioverdict.llm.types import ProviderRequest


class Answer(BaseModel):
    verdict: str


def status_error(cls, status: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


class StubSDK:
    """Records the kwargs of messages.parse and returns / raises what it was told."""

    def __init__(self, result=None, error=None):
        self.kwargs = None
        self._result, self._error = result, error
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return self._result


OK = Answer(verdict="ok")


def reply(stop="end_turn", parsed=OK):
    return SimpleNamespace(
        stop_reason=stop,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        model="claude-x",
    )


def request(model: str, **kw) -> ProviderRequest:
    return ProviderRequest(
        model=model, prompt="p", schema=Answer, effort="high", temperature=0.0, **kw
    )


def test_sonnet_gets_effort_but_no_temperature() -> None:
    sdk = StubSDK(reply())
    AnthropicProvider(sdk).complete(request("claude-sonnet-5-5"))
    assert sdk.kwargs["output_config"] == {"effort": "high"}
    assert "temperature" not in sdk.kwargs
    assert sdk.kwargs["output_format"] is Answer


def test_haiku_gets_temperature_but_no_effort() -> None:
    sdk = StubSDK(reply())
    AnthropicProvider(sdk).complete(request("claude-haiku-4-5"))
    assert sdk.kwargs["temperature"] == 0.0
    assert "output_config" not in sdk.kwargs


def test_capability_rules() -> None:
    assert not accepts_sampling("claude-opus-5-5") and accepts_sampling("claude-haiku-4-5")
    assert supports_effort("claude-sonnet-5-5") and not supports_effort("claude-haiku-4-5")


def test_response_is_mapped_to_json_text_and_tokens() -> None:
    out = AnthropicProvider(StubSDK(reply())).complete(request("claude-haiku-4-5"))
    assert (out.text, out.input_tokens, out.output_tokens) == ('{"verdict":"ok"}', 11, 7)


def test_refusal_and_truncation_and_empty_parse() -> None:
    with pytest.raises(RefusalError):
        AnthropicProvider(StubSDK(reply("refusal", None))).complete(request("claude-haiku-4-5"))
    with pytest.raises(FatalProviderError, match="max_tokens"):
        AnthropicProvider(StubSDK(reply("max_tokens", None))).complete(request("claude-haiku-4-5"))
    with pytest.raises(InvalidOutputError):
        AnthropicProvider(StubSDK(reply("end_turn", None))).complete(request("claude-haiku-4-5"))


@pytest.mark.parametrize(
    ("exc", "expected", "kind"),
    [
        (status_error(anthropic.RateLimitError, 429), TransientProviderError, "rate_limit"),
        (status_error(anthropic.InternalServerError, 500), TransientProviderError, "server"),
        (status_error(anthropic.APIStatusError, 529), TransientProviderError, "server"),
        (status_error(anthropic.APIStatusError, 402), TransientProviderError, "quota"),
        (status_error(anthropic.AuthenticationError, 401), FatalProviderError, None),
        (status_error(anthropic.BadRequestError, 400), FatalProviderError, None),
        (status_error(anthropic.NotFoundError, 404), FatalProviderError, None),
    ],
)
def test_http_errors_are_classified(exc, expected, kind) -> None:
    classified = classify_error(exc)
    assert isinstance(classified, expected)
    assert getattr(classified, "kind", None) == kind


def test_timeouts_and_network_errors_are_transient() -> None:
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    assert classify_error(anthropic.APITimeoutError(request=req)).kind == "timeout"
    assert classify_error(anthropic.APIConnectionError(request=req)).kind == "server"


def test_sdk_errors_are_raised_classified_from_complete() -> None:
    sdk = StubSDK(error=status_error(anthropic.RateLimitError, 429))
    with pytest.raises(TransientProviderError):
        AnthropicProvider(sdk).complete(request("claude-haiku-4-5"))


def test_a_refusal_names_the_safety_category() -> None:
    refused = reply("refusal", None)
    refused.stop_details = SimpleNamespace(category="bio")
    with pytest.raises(RefusalError, match="category: bio"):
        AnthropicProvider(StubSDK(refused)).complete(request("claude-sonnet-5-5"))
