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


class StepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(min_length=1)  # primary first, then failovers
    effort: str | None = "medium"
    temperature: float | None = 0.0
    max_tokens: int = 8000
    max_validation_retries: int = 2  # extra tries on invalid JSON, on the same model
    timeout_s: float = 90.0  # the agent timeout from the plan


_EXTRACTION = StepConfig(models=[HAIKU], effort=None, max_tokens=4000)
_REASONING = StepConfig(models=[SONNET], effort="medium", max_tokens=16000)
_SYNTHESIS = StepConfig(models=[SONNET], effort="high", max_tokens=16000)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: dict[str, StepConfig]
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_PRICES))
    budget_usd: float = 5.0  # RUN_BUDGET_USD
    breaker_threshold: int = 3  # consecutive failures that open a provider's breaker
    breaker_cooldown_s: float = 180.0  # "a few minutes"

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
        """Roles from docs/cost.md with the models that have an adapter today (Anthropic).

        TODO: the entailment judge must come from a different provider than the generator; it is
        added with the second adapter (B8), not faked here.
        """
        config = cls(
            steps={
                "resolver": _EXTRACTION,
                "extraction": _EXTRACTION,
                "reasoning": _REASONING,
                "reasoning.mechanism": _REASONING,
                "reasoning.translation": _REASONING,
                "skeptic": _SYNTHESIS,
                "chair": _SYNTHESIS,
                "synthesis": _SYNTHESIS,
            },
            budget_usd=float(os.environ.get("RUN_BUDGET_USD", "5")),
        )
        config.validate_prices()
        return config
