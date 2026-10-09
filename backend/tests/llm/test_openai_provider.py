from types import SimpleNamespace

import httpx2
import openai
import pytest
from pydantic import BaseModel

from bioverdict.llm.errors import (
    FatalProviderError,
    InvalidOutputError,
    OutputTruncatedError,
    RefusalError,
    TransientProviderError,
)
from bioverdict.llm.providers.openai import (
    SCHEMA_NAME,
    OpenAIProvider,
    classify_error,
    configured_key,
)
from bioverdict.llm.types import ProviderRequest


class Answer(BaseModel):
    verdict: str
    score: int = 0  # a default: the strict form must still list it as required


def status_error(cls, status: int):
    request = httpx2.Request("POST", "https://gateway.example/v1/chat/completions")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


class StubSDK:
    def __init__(self, result=None, error=None):
        self.kwargs = None
        self._result, self._error = result, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return self._result


def reply(finish="stop", text='{"verdict": "ok", "score": 2}', tokens=(11, 7), refusal=None):
    message = SimpleNamespace(content=text, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=tokens[0], completion_tokens=tokens[1]),
        model="gpt-6-luna",
    )


def request(**kw) -> ProviderRequest:
    base = {
        "model": "gpt-6-luna",
        "prompt": "p",
        "schema": Answer,
        "effort": "low",
        "temperature": 0.0,
    }
    return ProviderRequest(**(base | kw))


def test_the_request_has_what_the_gateway_accepts_and_nothing_it_rejects() -> None:
    sdk = StubSDK(reply())
    OpenAIProvider(sdk).complete(request(system="Be brief.", max_tokens=1234))
    sent = sdk.kwargs
    assert sent["max_completion_tokens"] == 1234 and "max_tokens" not in sent
    assert "temperature" not in sent  # the gateway answers 502 and charges for it
    assert sent["reasoning_effort"] == "low"
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]
    fmt = sent["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == SCHEMA_NAME


def test_the_schema_is_strict_with_every_field_required() -> None:
    sdk = StubSDK(reply())
    OpenAIProvider(sdk).complete(request())
    schema = sdk.kwargs["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"verdict", "score"}  # `score` has a default in Python


def test_no_effort_means_no_reasoning_parameter() -> None:
    sdk = StubSDK(reply())
    OpenAIProvider(sdk).complete(request(effort=None))
    assert "reasoning_effort" not in sdk.kwargs
    OpenAIProvider(sdk).complete(request(effort="max"))  # not a level this API knows
    assert "reasoning_effort" not in sdk.kwargs


def test_response_is_mapped_to_json_text_and_tokens() -> None:
    out = OpenAIProvider(StubSDK(reply())).complete(request())
    assert (out.text, out.input_tokens, out.output_tokens) == (
        '{"verdict":"ok","score":2}',
        11,
        7,
    )
    assert out.model == "gpt-6-luna"


@pytest.mark.parametrize(
    ("finish", "text", "refusal", "error"),
    [
        ("stop", "I cannot help with that.", "I cannot help with that.", RefusalError),
        ("content_filter", None, None, RefusalError),
        ("length", '{"verdict": "ok', None, OutputTruncatedError),  # cut off mid-JSON
        ("stop", "", None, InvalidOutputError),
        ("stop", "not json", None, InvalidOutputError),
        ("stop", '{"verdict": 3, "score": 1}', None, InvalidOutputError),  # wrong type
    ],
)
def test_an_unusable_answer_is_classified_and_still_carries_its_tokens(
    finish, text, refusal, error
) -> None:
    sdk = StubSDK(reply(finish, text, tokens=(1000, 4000), refusal=refusal))
    with pytest.raises(error) as info:
        OpenAIProvider(sdk).complete(request())
    assert (info.value.input_tokens, info.value.output_tokens) == (1000, 4000)


@pytest.mark.parametrize(
    ("exc", "expected", "kind"),
    [
        (status_error(openai.RateLimitError, 429), TransientProviderError, "rate_limit"),
        (status_error(openai.InternalServerError, 502), TransientProviderError, "server"),
        (status_error(openai.APIStatusError, 503), TransientProviderError, "server"),
        (status_error(openai.APIStatusError, 402), TransientProviderError, "quota"),
        (status_error(openai.AuthenticationError, 401), FatalProviderError, None),
        (status_error(openai.BadRequestError, 400), FatalProviderError, None),
        (status_error(openai.NotFoundError, 404), FatalProviderError, None),
    ],
)
def test_http_errors_are_classified(exc, expected, kind) -> None:
    classified = classify_error(exc)
    assert isinstance(classified, expected) and getattr(classified, "kind", None) == kind


def test_timeouts_and_network_errors_are_transient() -> None:
    req = httpx2.Request("POST", "https://gateway.example/v1/chat/completions")
    assert classify_error(openai.APITimeoutError(request=req)).kind == "timeout"
    assert classify_error(openai.APIConnectionError(request=req)).kind == "server"


def test_sdk_errors_are_raised_classified_from_complete() -> None:
    sdk = StubSDK(error=status_error(openai.RateLimitError, 429))
    with pytest.raises(TransientProviderError):
        OpenAIProvider(sdk).complete(request())


def test_the_key_comes_from_the_team_variable_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEAM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert configured_key() is None
    monkeypatch.setenv("OPENAI_API_KEY", "second")
    assert configured_key() == "second"
    monkeypatch.setenv("TEAM_API_KEY", "first")
    assert configured_key() == "first"
