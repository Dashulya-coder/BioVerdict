"""Error classes of the LLM layer. How an error is classified decides what the client does."""

from __future__ import annotations


class LLMError(Exception):
    """Base class of every error raised by the LLM layer."""


class TransientProviderError(LLMError):
    """429, quota, 5xx or timeout: fail over to the next model and count against the breaker."""

    def __init__(self, message: str, kind: str = "server") -> None:
        super().__init__(message)
        self.kind = kind  # rate_limit | quota | server | timeout


class FatalProviderError(LLMError):
    """Authentication, permission or a bad request: failing over would not help."""


class RefusalError(LLMError):
    """The model declined (safety classifier). Try another model; the provider is healthy."""


class InvalidOutputError(LLMError):
    """The answer is not valid JSON for the schema. Retried on the same model with feedback."""


class BudgetExceededError(LLMError):
    """The per-run spending cap is reached; no further call is made."""


class ConfigError(LLMError):
    """The configuration cannot work (unknown step, unpriced model, missing provider)."""


class AllModelsFailedError(LLMError):
    """Every model in the step's chain failed or was skipped by an open breaker."""

    def __init__(self, step: str, attempts: list[str]) -> None:
        super().__init__(f"all models failed for step {step!r}: " + "; ".join(attempts))
        self.step = step
        self.attempts = attempts
