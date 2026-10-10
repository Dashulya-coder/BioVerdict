"""The model of a live run: the real client with its cache, call log, budget and deadline.

A missing key is a configuration error that is reported as such. A live run never falls back to
canned answers.
"""

from __future__ import annotations

import os
from pathlib import Path

from bioverdict import settings
from bioverdict.contracts import LLM
from bioverdict.llm import ConfigError, LLMClient, LLMConfig
from bioverdict.llm.cache import DiskCache
from bioverdict.llm.call_log import SqliteCallLog
from bioverdict.llm.providers.anthropic import AnthropicProvider
from bioverdict.llm.providers.openai import OpenAIProvider, configured_key

ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
PROVIDER_VARIABLE = "LLM_PROVIDER"  # `anthropic` or `openai`; unset: the one with a key


def select_provider() -> str | None:
    """Which provider a live run uses, or None when no key is set.

    `LLM_PROVIDER` decides when it is set; otherwise the Anthropic key wins, then the key of the
    OpenAI-compatible gateway (`TEAM_API_KEY`, then `OPENAI_API_KEY`).
    """
    chosen = os.environ.get(PROVIDER_VARIABLE, "").strip().lower()
    if chosen:
        if chosen not in {"anthropic", "openai"}:
            raise ConfigError(f"{PROVIDER_VARIABLE}={chosen!r}: use 'anthropic' or 'openai'")
        return chosen
    if os.environ.get(ANTHROPIC_KEY):
        return "anthropic"
    if configured_key():
        return "openai"
    return None


def key_variable(provider: str) -> str:
    return ANTHROPIC_KEY if provider == "anthropic" else "TEAM_API_KEY (or OPENAI_API_KEY)"


def has_key(provider: str) -> bool:
    return (
        bool(os.environ.get(ANTHROPIC_KEY)) if provider == "anthropic" else bool(configured_key())
    )


def require_configured() -> None:
    """Raise before a run is created when it could not make its first model call."""
    provider = select_provider()
    if provider is None:
        raise ConfigError(
            f"no model key is set ({ANTHROPIC_KEY}, or TEAM_API_KEY for the gateway): "
            "a live run needs a model (see .env.example)"
        )
    if not has_key(provider):
        raise ConfigError(f"{key_variable(provider)} is not set: a live run needs a model")


def other_provider(provider: str) -> str | None:
    """The vendor that can judge `provider`'s claims: the other one, when its key is set."""
    other = "openai" if provider == "anthropic" else "anthropic"
    return other if has_key(other) else None


def live_llm(run_id: str, db_path: Path | None = None) -> LLM:
    """A client for one run: its budget and deadline are counted for this run only.

    When both vendors have a key the entailment judge runs on the vendor that did not write the
    claims; with one key it runs on a stronger model of the same vendor (see `judge_vendor`).
    """
    require_configured()
    provider = select_provider()
    assert provider is not None
    adapters = {"anthropic": AnthropicProvider, "openai": OpenAIProvider}
    config = LLMConfig.for_provider(provider)
    providers = {provider: adapters[provider]()}
    judge = other_provider(provider)
    if judge is not None:
        config = config.with_judge_from(LLMConfig.for_provider(judge))
        providers[judge] = adapters[judge]()
    client = LLMClient(
        config,
        providers,
        cache=DiskCache(settings.cache_dir() / "llm"),
        call_log=SqliteCallLog(db_path or settings.db_path()),
    )
    return client.bind(run_id)


def judge_vendor(provider: str) -> str:
    """Which vendor judges a run, for the runbook and the doctor: 'other' or 'same'."""
    return "other" if other_provider(provider) else "same"
