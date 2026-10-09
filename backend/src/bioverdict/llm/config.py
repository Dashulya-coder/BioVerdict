"""Per-step model chains, prices and limits (ADR-004, docs/cost.md).

The first model of a step is the primary; the rest are failovers in order. Model references
look like 'provider:model'. Roles are starting hypotheses until the bake-off in docs/cost.md.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.llm.errors import ConfigError

HAIKU = "anthropic:claude-haiku-4-5"
SONNET = "anthropic:claude-sonnet-5-5"
OPUS = "anthropic:claude-opus-5-5"


# The hackathon gateway (an OpenAI-compatible endpoint); the four models it lists.
LUNA = "openai:gpt-6-luna"
SOL = "openai:gpt-6.1-sol"
ASTRA = "openai:gpt-6-astra"
MINI = "openai:gpt-5-mini"


# The gateway rejects a request above about 16,180 characters (the text of every message plus the
# response schema in compact JSON plus about 100 of its own), measured 2026-10-09; the margin keeps
# an estimate that is a little low from costing a refused request.
GATEWAY_MAX_OUTPUT = (
    4096  # the gateway refuses max_completion_tokens above ~4,096 (4,000 ok, 5,000 not)
)
GATEWAY_INPUT_CHARS = 16_000


def _input_limit(default: int | None) -> int | None:
    value = os.environ.get("LLM_MAX_INPUT_CHARS", "").strip()
    if not value:
        return default
    try:
        return int(value) if int(value) > 0 else None  # 0 or less: no limit
    except ValueError as exc:
        raise ConfigError(f"LLM_MAX_INPUT_CHARS={value!r} is not a whole number") from exc


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_mtok: float
    output_per_mtok: float


# USD per 1M tokens, Anthropic first-party list prices (docs/cost.md, checked 2026-10-06).
DEFAULT_PRICES: dict[str, ModelPrice] = {
    HAIKU: ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
    SONNET: ModelPrice(input_per_mtok=2.0, output_per_mtok=10.0),
    OPUS: ModelPrice(input_per_mtok=4.0, output_per_mtok=20.0),
}


# USD per 1M tokens (docs/cost.md). gpt-5-mini is a public list price that has not been checked
# against the gateway; the gateway reserves and charges its own amounts, so compare with its
# portal after a run.
GATEWAY_PRICES: dict[str, ModelPrice] = {
    LUNA: ModelPrice(input_per_mtok=0.10, output_per_mtok=0.50),
    SOL: ModelPrice(input_per_mtok=2.0, output_per_mtok=10.0),
    ASTRA: ModelPrice(input_per_mtok=10.0, output_per_mtok=50.0),
    MINI: ModelPrice(input_per_mtok=0.25, output_per_mtok=2.0),
}


class StepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(min_length=1)  # primary first, then failovers
    effort: str | None = "medium"
    temperature: float | None = 0.0
    max_tokens: int = 8000
    max_validation_retries: int = 2  # extra tries on invalid JSON, on the same model
    timeout_s: float = 90.0  # the agent timeout from the plan


# Collection is short (90 s, the agent timeout of the plan); reasoning writes up to 16k tokens
# at medium or high effort and needs more. The run deadline caps the sum either way.
_EXTRACTION = StepConfig(models=[HAIKU], effort=None, max_tokens=4000, timeout_s=90.0)
# A second model absorbs refusals: the bio safety classifier can refuse mechanism-of-action text.
_REASONING = StepConfig(models=[SONNET, OPUS], effort="medium", max_tokens=16000, timeout_s=180.0)
_SYNTHESIS = StepConfig(models=[SONNET, OPUS], effort="high", max_tokens=16000, timeout_s=240.0)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: dict[str, StepConfig]
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_PRICES))
    budget_usd: float = 5.0  # RUN_BUDGET_USD
    breaker_threshold: int = 3  # consecutive failures that open a provider's breaker
    breaker_cooldown_s: float = 180.0  # "a few minutes"
    run_timeout_s: float = 420.0  # RUN_TIMEOUT_S: hard wall-clock limit per run
    # Characters an endpoint accepts in one request (messages and response schema together); None:
    # no known limit. The gateway's is measured; LLM_MAX_INPUT_CHARS overrides it.
    max_input_chars: int | None = None

    def step(self, name: str) -> StepConfig:
        try:
            return self.steps[name]
        except KeyError:
            raise ConfigError(f"no model configured for step {name!r}") from None

    def validate_prices(self) -> None:
        """Every model in use needs a price, or the budget cap cannot work."""
        for name, step in self.steps.items():
            for ref in step.models:
                if ref not in self.prices:
                    raise ConfigError(f"step {name!r}: model {ref!r} has no price")

    @classmethod
    def default(cls) -> LLMConfig:
        """Roles from docs/cost.md on Anthropic's models (see `for_provider` for the others).

        TODO: the entailment judge must come from a different model family than the generator;
        it is added with B8, not faked here.
        """
        return cls._build(_EXTRACTION, _REASONING, _SYNTHESIS, dict(DEFAULT_PRICES))

    @classmethod
    def for_provider(cls, provider: str) -> LLMConfig:
        """The roles on one provider's models: `anthropic`, or `openai` (the hackathon gateway)."""
        if provider == "anthropic":
            return cls.default()
        if provider == "openai":
            # Reasoning models spend hidden tokens inside max_completion_tokens, and the gateway
            # reserves money for the whole of it: keep the limits as tight as the answers allow.
            extraction = StepConfig(models=[LUNA], effort="low", max_tokens=3000, timeout_s=90.0)
            reasoning = StepConfig(
                models=[SOL, MINI], effort="low", max_tokens=GATEWAY_MAX_OUTPUT, timeout_s=180.0
            )
            synthesis = StepConfig(
                models=[SOL, MINI], effort="high", max_tokens=GATEWAY_MAX_OUTPUT, timeout_s=240.0
            )
            config = cls._build(extraction, reasoning, synthesis, dict(GATEWAY_PRICES))
            config.max_input_chars = _input_limit(GATEWAY_INPUT_CHARS)
            return config
        raise ConfigError(f"unknown provider {provider!r}: use 'anthropic' or 'openai'")

    @classmethod
    def _build(
        cls,
        extraction: StepConfig,
        reasoning: StepConfig,
        synthesis: StepConfig,
        prices: dict[str, ModelPrice],
    ) -> LLMConfig:
        config = cls(
            steps={
                "resolver": extraction,
                "extraction": extraction,
                "reasoning": reasoning,
                "reasoning.mechanism": reasoning,
                "reasoning.translation": reasoning,
                "reasoning.clinical": reasoning,
                "reasoning.competition": reasoning,
                "reasoning.classify": reasoning,
                "skeptic": synthesis,
                "chair": synthesis,
                "synthesis": synthesis,
            },
            prices=prices,
            budget_usd=float(os.environ.get("RUN_BUDGET_USD", "5")),
            run_timeout_s=float(os.environ.get("RUN_TIMEOUT_S", "420")),
        )
        config.validate_prices()
        return config
