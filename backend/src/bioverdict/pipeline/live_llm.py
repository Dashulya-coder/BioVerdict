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

KEY = "ANTHROPIC_API_KEY"  # the only provider with an adapter today


def require_configured() -> None:
    """Raise before a run is created when it could not make its first model call."""
    if not os.environ.get(KEY):
        raise ConfigError(f"{KEY} is not set: a live run needs a model (see .env.example)")


def live_llm(run_id: str, db_path: Path | None = None) -> LLM:
    """A client for one run: its budget and deadline are counted for this run only."""
    require_configured()
    client = LLMClient(
        LLMConfig.default(),
        {AnthropicProvider.name: AnthropicProvider()},
        cache=DiskCache(settings.cache_dir() / "llm"),
        call_log=SqliteCallLog(db_path or settings.db_path()),
    )
    return client.bind(run_id)
