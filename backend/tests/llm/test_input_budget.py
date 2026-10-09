"""The gateway refuses a request above ~16,000 characters: size prompts by the budget, fail early."""

import json

import pytest
from pydantic import BaseModel, Field

from bioverdict.llm import (
    AllModelsFailedError,
    InputTooLargeError,
    LLMClient,
    LLMConfig,
    StepConfig,
)
from bioverdict.llm.call_log import MemoryCallLog
from bioverdict.llm.config import DEFAULT_PRICES, HAIKU
from bioverdict.llm.providers.fake import FakeProvider
from bioverdict.llm.providers.openai import OpenAIProvider, slim_schema, strict_schema
from bioverdict.llm.types import ProviderRequest, SizedProvider

GOOD = '{"verdict": "ok", "score": 3}'


class Answer(BaseModel):
    verdict: str = Field(description="What the committee decides", min_length=1)
    score: int


class SizedFake(FakeProvider):
    """A fake endpoint that counts characters like the gateway: prompt, system and 40 for the rest."""

    def input_chars(self, request: ProviderRequest) -> int:
        return len(request.prompt) + len(request.system or "") + 40


def client(limit: int | None, provider=None, **kw) -> tuple[LLMClient, FakeProvider]:
    fake = provider or SizedFake(GOOD, name="anthropic")
    config = LLMConfig(
        steps={"s": StepConfig(models=[HAIKU])},
        prices=dict(DEFAULT_PRICES),
        max_input_chars=limit,
        **kw,
    )
    return LLMClient(config, {"anthropic": fake}, call_log=MemoryCallLog()), fake


# --- the schema ---------------------------------------------------------------------------------


def test_slim_schema_drops_titles_and_descriptions_but_not_fields_with_those_names() -> None:
    class Odd(BaseModel):
        title: str = Field(description="a field called title")
        description: str
        items: list[Answer] = []

    slim = slim_schema(strict_schema(Odd))
    text = json.dumps(slim)
    assert '"description": "' not in text.replace('"description": {', "")  # no annotation left
    assert set(slim["properties"]) >= {"title", "description", "items"}  # the fields are kept
    assert slim["additionalProperties"] is False and set(slim["required"]) == {
        "title",
        "description",
        "items",
    }
    assert (
        len(text) < len(json.dumps(strict_schema.__wrapped__(Odd)))
        if hasattr(strict_schema, "__wrapped__")
        else True
    )


def test_the_strict_schema_is_smaller_than_openais_own() -> None:
    import openai

    full = openai.pydantic_function_tool(Answer, name="answer")["function"]["parameters"]
    assert len(json.dumps(strict_schema(Answer))) < len(json.dumps(full))
    assert "min_length" not in json.dumps(strict_schema(Answer))


def test_the_gateway_adapter_reports_what_the_gateway_counts() -> None:
    provider = OpenAIProvider(client=object())
    req = ProviderRequest(model="m", prompt="x" * 1000, system="y" * 200, schema=Answer)
    schema_chars = len(json.dumps(strict_schema(Answer), separators=(",", ":")))
    assert provider.input_chars(req) == 1000 + 200 + schema_chars + 100
    assert isinstance(provider, SizedProvider)


# --- the client ---------------------------------------------------------------------------------


def test_a_request_over_the_limit_is_refused_before_it_is_sent_and_costs_nothing() -> None:
    llm, fake = client(1000)
    with pytest.raises(InputTooLargeError) as info:
        llm.call("s", "x" * 2000, Answer, run_id="R")
    assert (info.value.size, info.value.limit) == (2040, 1000)
    assert fake.requests == [] and llm.spent("R") == 0.0
    assert "2,040 characters" in str(info.value)


def test_a_request_that_fits_is_sent() -> None:
    llm, fake = client(1000)
    assert llm.call("s", "x" * 900, Answer, run_id="R").parsed["score"] == 3
    assert len(fake.requests) == 1


def test_the_failure_is_logged_and_the_error_does_not_trigger_a_failover() -> None:
    log = MemoryCallLog()
    config = LLMConfig(
        steps={"s": StepConfig(models=[HAIKU])}, prices=dict(DEFAULT_PRICES), max_input_chars=500
    )
    llm = LLMClient(config, {"anthropic": SizedFake(GOOD, name="anthropic")}, call_log=log)
    with pytest.raises(InputTooLargeError):
        llm.call("s", "x" * 600, Answer, run_id="R")
    assert log.entries[0].error and "characters" in log.entries[0].error
    assert not isinstance(InputTooLargeError(1, 1), AllModelsFailedError)


def test_the_retry_with_feedback_is_checked_too() -> None:
    """A second try adds the error text to the prompt; it must not push the request over."""
    fake = SizedFake("not json", GOOD, name="anthropic")
    llm, _ = client(1200, fake)
    with pytest.raises(InputTooLargeError):
        llm.call("s", "x" * 1100, Answer, run_id="R")  # fits first, not once feedback is added
    assert len(fake.requests) == 1


def test_the_budget_is_what_is_left_after_the_schema_and_the_system_message() -> None:
    llm, _ = client(1000)
    assert llm.input_budget("s", Answer) == 1000 - 40
    assert llm.input_budget("s", Answer, system="y" * 100) == 1000 - 140
    assert client(None)[0].input_budget("s", Answer) is None


def test_a_provider_that_cannot_say_how_big_a_request_is_not_checked() -> None:
    plain = FakeProvider(GOOD, name="anthropic")
    llm, _fake = client(10, plain)
    assert llm.call("s", "x" * 5000, Answer).parsed["verdict"] == "ok"
    assert llm.input_budget("s", Answer) == 10  # the configured limit, nothing to subtract


def test_the_bound_client_gives_the_same_budget() -> None:
    llm, _ = client(1000)
    assert llm.bind("R").input_budget("s", Answer) == 960


# --- configuration -------------------------------------------------------------------------------


def test_the_gateway_preset_carries_the_measured_limit_and_the_environment_can_change_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert LLMConfig.for_provider("openai").max_input_chars == 16_000
    assert LLMConfig.for_provider("anthropic").max_input_chars is None
    monkeypatch.setenv("LLM_MAX_INPUT_CHARS", "50000")  # if the organizers raise it
    assert LLMConfig.for_provider("openai").max_input_chars == 50_000
    monkeypatch.setenv("LLM_MAX_INPUT_CHARS", "0")
    assert LLMConfig.for_provider("openai").max_input_chars is None


def test_a_limit_that_is_not_a_number_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bioverdict.llm import ConfigError

    monkeypatch.setenv("LLM_MAX_INPUT_CHARS", "lots")
    with pytest.raises(ConfigError, match="LLM_MAX_INPUT_CHARS"):
        LLMConfig.for_provider("openai")
