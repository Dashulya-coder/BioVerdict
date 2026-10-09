"""Error classes of the LLM layer. How an error is classified decides what the client does."""

from __future__ import annotations


class LLMError(Exception):
    """Base class of every error raised by the LLM layer.

    An error raised after the provider answered (a refusal, a cut-off answer, unreadable JSON)
    still cost money: the adapter attaches the tokens with `with_usage` so the client can charge
    the budget and the log for them.
    """

    input_tokens: int = 0
    output_tokens: int = 0

    def with_usage(self, input_tokens: int, output_tokens: int):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        return self


class TransientProviderError(LLMError):
    """429, quota, 5xx or timeout: fail over to the next model and count against the breaker."""

    def __init__(self, message: str, kind: str = "server") -> None:
        super().__init__(message)
        self.kind = kind  # rate_limit | quota | server | timeout


class FatalProviderError(LLMError):
    """Authentication, permission or a bad request: failing over would not help."""


class InputTooLargeError(FatalProviderError):
    """The request is longer than the endpoint accepts. Detected before it is sent, so it costs
    nothing; the caller must send less (see `LLMClient.input_budget`)."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"the request is {size:,} characters, the endpoint accepts {limit:,}")
        self.size, self.limit = size, limit


class RefusalError(LLMError):
    """The model declined (safety classifier). Try another model; the provider is healthy."""


class InvalidOutputError(LLMError):
    """The answer is not valid JSON for the schema. Retried on the same model with feedback."""


class OutputTruncatedError(InvalidOutputError):
    """The answer hit the output-token limit (reasoning tokens count). Retried with a request to
    write less: the same limit with the same prompt would be cut off again."""


class BudgetExceededError(LLMError):
    """The per-run spending cap is reached; no further call is made."""


class RunTimeoutError(LLMError):
    """The whole run exceeded its deadline (RUN_TIMEOUT_S); no further model call is made."""


class ConfigError(LLMError):
    """The configuration cannot work (unknown step, unpriced model, missing provider)."""


class AllModelsFailedError(LLMError):
    """Every model in the step's chain failed or was skipped by an open breaker."""

    def __init__(self, step: str, attempts: list[str]) -> None:
        super().__init__(f"all models failed for step {step!r}: " + "; ".join(attempts))
        self.step = step
        self.attempts = attempts
