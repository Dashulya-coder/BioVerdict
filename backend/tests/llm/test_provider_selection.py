import pytest

from bioverdict.llm import ConfigError, LLMConfig
from bioverdict.llm.config import LUNA, MINI, SOL
from bioverdict.llm.providers.anthropic import AnthropicProvider
from bioverdict.llm.providers.openai import OpenAIProvider
from bioverdict.pipeline.live_llm import live_llm, require_configured, select_provider

STEPS = {
    "resolver",
    "extraction",
    "reasoning",
    "reasoning.mechanism",
    "reasoning.translation",
    "reasoning.clinical",
    "reasoning.competition",
    "reasoning.classify",
    "skeptic",
    "chair",
    "synthesis",
}


def test_without_any_key_no_provider_is_chosen_and_a_live_run_is_refused() -> None:
    assert select_provider() is None
    with pytest.raises(ConfigError, match="no model key is set"):
        require_configured()


def test_the_provider_follows_the_key_that_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_API_KEY", "team")
    assert select_provider() == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude")
    assert select_provider() == "anthropic"  # the first-party key wins when both exist


def test_the_environment_can_force_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAM_API_KEY", "team")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude")
    monkeypatch.setenv("LLM_PROVIDER", "OpenAI")
    assert select_provider() == "openai"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ConfigError, match="use 'anthropic' or 'openai'"):
        select_provider()


def test_a_forced_provider_without_its_key_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ConfigError, match="TEAM_API_KEY"):
        require_configured()


def test_a_live_client_uses_the_adapter_of_the_chosen_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("TEAM_API_KEY", "team")
    gateway = live_llm("R-1", tmp_path / "t.db")
    assert isinstance(next(iter(gateway._client._providers.values())), OpenAIProvider)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude")
    claude = live_llm("R-2", tmp_path / "t.db")
    assert isinstance(next(iter(claude._client._providers.values())), AnthropicProvider)


def test_the_gateway_preset_covers_every_step_with_priced_gateway_models() -> None:
    config = LLMConfig.for_provider("openai")
    assert set(config.steps) == STEPS
    for step in config.steps.values():
        assert all(ref.startswith("openai:") for ref in step.models)
    config.validate_prices()
    assert config.step("extraction").models == [LUNA]
    assert config.step("reasoning.clinical").models == [SOL, MINI]  # a second model for refusals


def test_the_gateway_preset_keeps_token_limits_tight() -> None:
    """The gateway reserves money for max_completion_tokens, hidden reasoning tokens included."""
    config = LLMConfig.for_provider("openai")
    assert config.step("extraction").max_tokens <= 3000
    assert config.step("synthesis").max_tokens <= 8000


def test_the_anthropic_preset_is_the_default_and_unknown_providers_are_refused() -> None:
    assert LLMConfig.for_provider("anthropic") == LLMConfig.default()
    with pytest.raises(ConfigError, match="unknown provider"):
        LLMConfig.for_provider("gemini")
