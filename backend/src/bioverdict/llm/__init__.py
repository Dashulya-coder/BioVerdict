"""LLM access layer (ADR-004). Use `LLMClient.call`; nothing else talks to a model."""

from bioverdict.llm.client import LLMClient
from bioverdict.llm.config import LLMConfig, StepConfig
from bioverdict.llm.errors import (
    AllModelsFailedError,
    BudgetExceededError,
    ConfigError,
    FatalProviderError,
    InputTooLargeError,
    InvalidOutputError,
    LLMError,
    RefusalError,
    RunTimeoutError,
    TransientProviderError,
)
from bioverdict.llm.fake import FakeLLM

__all__ = [
    "AllModelsFailedError",
    "BudgetExceededError",
    "ConfigError",
    "FakeLLM",
    "FatalProviderError",
    "InputTooLargeError",
    "InvalidOutputError",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "RefusalError",
    "RunTimeoutError",
    "StepConfig",
    "TransientProviderError",
]
