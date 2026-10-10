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


# The gateway refuses max_completion_tokens above 4,096 (4,097 is refused; measured 2026-10-09 and
# again 2026-10-10). Hidden reasoning tokens count inside it.
GATEWAY_MAX_OUTPUT = 4096
# The gateway refused a request above about 16,180 characters on 2026-10-09; on 2026-10-10 it took
# 128,000 on gpt-6.1-sol and 256,000 on gpt-6-luna. No limit by default; LLM_MAX_INPUT_CHARS puts
# one back if the gateway does.
GATEWAY_INPUT_CHARS: int | None = None
# What bounds a prompt now is the answer, which grows with what the prompt holds. A module batch
# of 16,000 characters was cut off at 4,096 tokens and retried short twice in two live runs
# (clinical on R-cf6f3be64e7b409f803f162134a0f174, translation on R-e0a3a432b1a6486da63da74805af1a04),
# so module and classification batches are 12,000 and more evidence means more batches.
GATEWAY_MODULE_CHARS = 12_000
GATEWAY_EXTRACTION_CHARS = 16_000  # its answers stayed under 900 of its 3,000 tokens
GATEWAY_SYNTHESIS_CHARS = 60_000  # the Chair: room for every claim of a run
# The Skeptic answers from the evidence it reads: 3,881 tokens from 60,000 (5 objections grounded),
# 1,532 from 30,000 (1 grounded). One run each; 45,000 is between, with room in the answer.
GATEWAY_SKEPTIC_CHARS = 45_000


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
    # Characters this step's prompts are built to (messages and schema), so that the answer fits
    # max_tokens; None: only the endpoint's limit, if it has one (`LLMClient.input_budget`).
    prompt_chars: int | None = None


# Collection is short (90 s, the agent timeout of the plan); reasoning writes up to 16k tokens
# at medium or high effort and needs more. The run deadline caps the sum either way.
_EXTRACTION = StepConfig(models=[HAIKU], effort=None, max_tokens=4000, timeout_s=90.0)
# A second model absorbs refusals: the bio safety classifier can refuse mechanism-of-action text.
_REASONING = StepConfig(models=[SONNET, OPUS], effort="medium", max_tokens=16000, timeout_s=180.0)
_SYNTHESIS = StepConfig(models=[SONNET, OPUS], effort="high", max_tokens=16000, timeout_s=240.0)
# The judge should not be the model that wrote the claims. Opus is the strongest model of the
# generator's vendor; `LLMConfig.with_judge_from` moves it to another vendor when a key exists.
_JUDGE = StepConfig(models=[OPUS], effort="high", max_tokens=8000, timeout_s=240.0)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: dict[str, StepConfig]
    prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_PRICES))
    budget_usd: float = 5.0  # RUN_BUDGET_USD
    breaker_threshold: int = 3  # consecutive failures that open a provider's breaker
    breaker_cooldown_s: float = 180.0  # "a few minutes"
    run_timeout_s: float = 900.0  # RUN_TIMEOUT_S: hard wall-clock limit per run (runs of the demo pair took 4 to 7 minutes)
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

    def with_judge_from(self, other: LLMConfig) -> LLMConfig:
        """This configuration, with the judge (and the prices it needs) from another vendor's.

        The claims are written by one vendor's models and checked by another's, so a systematic
        blind spot of the first is not shared by the checker.
        """
        steps = {**self.steps, "judge": other.step("judge")}
        prices = {**self.prices, **{m: other.prices[m] for m in other.step("judge").models}}
        config = self.model_copy(update={"steps": steps, "prices": prices})
        config.validate_prices()
        return config

    @classmethod
    def default(cls) -> LLMConfig:
        """Roles from docs/cost.md on Anthropic's models (see `for_provider` for the others).

        TODO: the entailment judge must come from a different model family than the generator;
        it is added with B8, not faked here.
        """
        return cls._build(_EXTRACTION, _REASONING, _SYNTHESIS, _JUDGE, dict(DEFAULT_PRICES))

    @classmethod
    def for_provider(cls, provider: str) -> LLMConfig:
        """The roles on one provider's models: `anthropic`, or `openai` (the hackathon gateway)."""
        if provider == "anthropic":
            return cls.default()
        if provider == "openai":
            # Reasoning models spend hidden tokens inside max_completion_tokens, and the gateway
            # reserves money for the whole of it: keep the limits as tight as the answers allow.
            extraction = StepConfig(
                models=[LUNA],
                effort="low",
                max_tokens=3000,
                timeout_s=90.0,
                prompt_chars=GATEWAY_EXTRACTION_CHARS,
            )
            reasoning = StepConfig(
                models=[SOL, MINI],
                effort="low",
                max_tokens=GATEWAY_MAX_OUTPUT,
                timeout_s=180.0,
                prompt_chars=GATEWAY_MODULE_CHARS,
            )
            synthesis = StepConfig(
                models=[SOL, MINI],
                effort="high",
                max_tokens=GATEWAY_MAX_OUTPUT,
                timeout_s=240.0,
                prompt_chars=GATEWAY_SYNTHESIS_CHARS,
            )
            # Not the model that writes the claims (gpt-6.1-sol): the strongest one the gateway
            # lists. A claim is a few hundred characters, so the 5x price is a few cents a run.
            # The judge sizes its own batches (verification/entailment.py: BATCH_CHARS).
            judge = StepConfig(
                models=[ASTRA, MINI], effort="high", max_tokens=GATEWAY_MAX_OUTPUT, timeout_s=240.0
            )
            config = cls._build(extraction, reasoning, synthesis, judge, dict(GATEWAY_PRICES))
            config.steps["skeptic"] = synthesis.model_copy(
                update={"prompt_chars": GATEWAY_SKEPTIC_CHARS}
            )
            config.max_input_chars = _input_limit(GATEWAY_INPUT_CHARS)
            return config
        raise ConfigError(f"unknown provider {provider!r}: use 'anthropic' or 'openai'")

    @classmethod
    def _build(
        cls,
        extraction: StepConfig,
        reasoning: StepConfig,
        synthesis: StepConfig,
        judge: StepConfig,
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
                "reasoning.unmet_need": reasoning,
                "reasoning.commercial": reasoning,
                "reasoning.classify": reasoning,
                "skeptic": synthesis,
                "chair": synthesis,
                "synthesis": synthesis,
                "judge": judge,
            },
            prices=prices,
            budget_usd=float(os.environ.get("RUN_BUDGET_USD", "5")),
            run_timeout_s=float(os.environ.get("RUN_TIMEOUT_S", "900")),
        )
        config.validate_prices()
        return config
