"""`llm.call(step, prompt, schema)`: the only way code talks to a model (ADR-004).

Order of events for one call: cache lookup, then the step's model chain. Per model: budget and
deadline check, provider call, schema validation (invalid JSON is retried on the same model with
feedback). Transient errors (429, quota, 5xx, timeout) fail over to the next model and count
against the provider's circuit breaker; auth and bad-request errors do not fail over.

Every attempt is paid for, so the result and the log carry the tokens and cost of all attempts of
the call (invalid answers and models that failed before a failover included), not only the last.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from bioverdict.llm.breaker import CircuitBreaker
from bioverdict.llm.budget import Budget, Deadline
from bioverdict.llm.cache import LLMCache, cache_key
from bioverdict.llm.call_log import CallLog, CallRecord
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
from bioverdict.llm.types import (
    Provider,
    ProviderRequest,
    ProviderResponse,
    SizedProvider,
    split_model_ref,
)
from bioverdict.store.models import LLMResult

_CHARS_PER_TOKEN = 3  # fewer than real text has, so a prompt is never under-counted


@dataclass
class _Usage:
    """Tokens and cost of every attempt of one `call`."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class LLMClient:
    def __init__(
        self,
        config: LLMConfig,
        providers: Mapping[str, Provider],
        *,
        cache: LLMCache | None = None,
        call_log: CallLog | None = None,
        breaker: CircuitBreaker | None = None,
        budget: Budget | None = None,
        deadline: Deadline | None = None,
    ) -> None:
        config.validate_prices()
        self._config = config
        self._providers = dict(providers)
        self._cache = cache
        self._log = call_log
        self._breaker = breaker or CircuitBreaker(
            config.breaker_threshold, config.breaker_cooldown_s
        )
        self._budget = budget or Budget(config.budget_usd)
        self._deadline = deadline or Deadline(config.run_timeout_s)
        self._mixed: set[str] = set()
        self._lock = threading.Lock()

    # -- public ---------------------------------------------------------------

    def call(
        self,
        step: str,
        prompt: str,
        schema: type[BaseModel],
        *,
        run_id: str | None = None,
        system: str | None = None,
    ) -> LLMResult:
        cfg = self._config.step(step)
        self._require_providers(step, cfg)
        started = time.perf_counter()

        def request_for(ref: str, text: str, timeout_s: float | None = None) -> ProviderRequest:
            return ProviderRequest(
                model=split_model_ref(ref)[1],
                prompt=text,
                schema=schema,
                system=system,
                effort=cfg.effort,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout_s=cfg.timeout_s if timeout_s is None else timeout_s,
            )

        primary = cfg.models[0]
        key = cache_key(primary, request_for(primary, prompt))
        hit = self._cache_lookup(key, schema)
        if hit is not None:
            result = hit.model_copy(
                update={
                    "step": step,
                    "cache_hit": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            if hit.failover_from is not None:  # the recorded answer came from a failover model
                self._mark_mixed(run_id)
            self._record(run_id, step, result, cfg, error=None)
            return result

        usage = _Usage()
        failures: list[str] = []
        attempts = 0
        first_failed: str | None = None
        for ref in cfg.models:
            provider_name, _ = split_model_ref(ref)
            if self._breaker.is_open(provider_name):
                failures.append(f"{ref}: circuit breaker open")
                first_failed = first_failed or ref
                continue
            try:
                response, used = self._ask_model(
                    ref, cfg, prompt, request_for, schema, run_id, usage
                )
            except (TransientProviderError, RefusalError, InvalidOutputError) as exc:
                attempts += getattr(exc, "attempts", 1)
                failures.append(f"{ref}: {type(exc).__name__}: {exc}")
                first_failed = first_failed or ref
                if isinstance(exc, TransientProviderError):
                    self._breaker.record_failure(provider_name)
                continue
            except (FatalProviderError, BudgetExceededError, RunTimeoutError) as exc:
                self._record_failure(run_id, step, ref, cfg, started, attempts + 1, usage, str(exc))
                raise
            attempts += used
            self._breaker.record_success(provider_name)
            result = self._build_result(
                step, ref, response, schema, started, attempts, first_failed, run_id, usage
            )
            if self._cache is not None:
                self._cache.put(key, result.model_dump(mode="json"))
            self._record(run_id, step, result, cfg, error=None)
            return result

        error = AllModelsFailedError(step, failures)
        self._record_failure(run_id, step, primary, cfg, started, attempts, usage, str(error))
        raise error

    def bind(self, run_id: str) -> BoundLLM:
        """A view of this client tied to one run, with the plain `LLM` contract signature.

        Callers that only know `call(step, prompt, schema)` (the collect agents) use it so
        their calls are still counted against the run's budget and logged with its run id.
        """
        return BoundLLM(self, run_id)

    def input_budget(
        self, step: str, schema: type[BaseModel], system: str | None = None
    ) -> int | None:
        """Characters left for the prompt of `step` after the response schema and the system
        message, or None if the endpoint has no known limit. Callers size their prompts by it:
        a request over the limit is refused before it is sent."""
        limit = self._config.max_input_chars
        if limit is None:
            return None
        cfg = self._config.step(step)
        provider = self._providers[split_model_ref(cfg.models[0])[0]]
        if not isinstance(provider, SizedProvider):
            return limit
        empty = ProviderRequest(
            model=split_model_ref(cfg.models[0])[1], prompt="", schema=schema, system=system
        )
        return max(0, limit - provider.input_chars(empty))

    def _check_size(self, provider: Provider, request: ProviderRequest) -> None:
        limit = self._config.max_input_chars
        if limit is not None and isinstance(provider, SizedProvider):
            size = provider.input_chars(request)
            if size > limit:
                raise InputTooLargeError(size, limit)

    def mixed_models(self, run_id: str | None) -> bool:
        """True when any call of the run was answered by a failover model (flag for the trace)."""
        with self._lock:
            return (run_id or "-") in self._mixed

    def spent(self, run_id: str | None) -> float:
        return self._budget.spent(run_id)

    # -- internals ------------------------------------------------------------

    def _mark_mixed(self, run_id: str | None) -> None:
        with self._lock:
            self._mixed.add(run_id or "-")

    def _require_providers(self, step: str, cfg: StepConfig) -> None:
        for ref in cfg.models:
            name, _ = split_model_ref(ref)
            if name not in self._providers:
                raise ConfigError(f"step {step!r} uses {ref!r} but provider {name!r} is not set up")

    def _ask_model(
        self,
        ref: str,
        cfg: StepConfig,
        prompt: str,
        request_for: Callable[..., ProviderRequest],
        schema: type[BaseModel],
        run_id: str | None,
        usage: _Usage,
    ) -> tuple[ProviderResponse, int]:
        """Call one model, retrying invalid JSON with feedback. Returns (response, attempts)."""
        provider = self._providers[split_model_ref(ref)[0]]
        text = prompt
        last: InvalidOutputError | None = None
        for attempt in range(1, cfg.max_validation_retries + 2):
            left = self._deadline.check(run_id)
            request = request_for(ref, text, min(cfg.timeout_s, left))
            self._check_size(provider, request)
            try:
                with self._budget.hold(run_id, self._worst_case(ref, cfg, text)):
                    try:
                        response = provider.complete(request)
                    except LLMError as exc:  # an answer that was unusable still cost money
                        self._charge_tokens(run_id, ref, exc.input_tokens, exc.output_tokens, usage)
                        raise
                    self._charge(run_id, ref, response, usage)
                schema.model_validate_json(response.text)
                return response, attempt
            except (ValidationError, InvalidOutputError) as exc:
                last = InvalidOutputError(str(exc))
                text = (
                    f"{prompt}\n\nYour previous answer was rejected: {_short(exc)}\n"
                    "Answer again with only a JSON object that matches the schema."
                )
        assert last is not None
        last.attempts = cfg.max_validation_retries + 1  # type: ignore[attr-defined]
        raise last

    def _worst_case(self, ref: str, cfg: StepConfig, prompt: str) -> float:
        """The most one call can cost: the whole prompt read and every allowed token written.
        Three characters a token over-counts the prompt, which is the safe side."""
        price = self._config.prices[ref]
        prompt_tokens = len(prompt) / _CHARS_PER_TOKEN
        return (
            prompt_tokens * price.input_per_mtok + cfg.max_tokens * price.output_per_mtok
        ) / 1_000_000

    def _charge(
        self, run_id: str | None, ref: str, response: ProviderResponse, usage: _Usage
    ) -> None:
        self._charge_tokens(run_id, ref, response.input_tokens, response.output_tokens, usage)

    def _charge_tokens(
        self, run_id: str | None, ref: str, input_tokens: int, output_tokens: int, usage: _Usage
    ) -> None:
        if not (input_tokens or output_tokens):
            return
        price = self._config.prices[ref]
        cost = (
            input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
        ) / 1_000_000
        self._budget.charge(run_id, cost)
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.cost_usd += cost

    def _cost(self, ref: str, response: ProviderResponse) -> float:
        price = self._config.prices[ref]
        return (
            response.input_tokens * price.input_per_mtok
            + response.output_tokens * price.output_per_mtok
        ) / 1_000_000

    def _build_result(
        self,
        step: str,
        ref: str,
        response: ProviderResponse,
        schema: type[BaseModel],
        started: float,
        attempts: int,
        first_failed: str | None,
        run_id: str | None,
        usage: _Usage,
    ) -> LLMResult:
        provider_name, _ = split_model_ref(ref)
        if first_failed is not None:
            self._mark_mixed(run_id)
        return LLMResult(
            step=step,
            provider=provider_name,
            model=response.model,
            parsed=schema.model_validate_json(response.text).model_dump(mode="json"),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
            cache_hit=False,
            failover_from=first_failed,
        )

    def _cache_lookup(self, key: str, schema: type[BaseModel]) -> LLMResult | None:
        if self._cache is None:
            return None
        raw = self._cache.get(key)
        if raw is None:
            return None
        try:
            result = LLMResult.model_validate(raw)
            schema.model_validate(result.parsed)
        except ValidationError:
            return None  # stale or damaged entry: treat as a miss
        return result

    def _record(
        self, run_id: str | None, step: str, result: LLMResult, cfg: StepConfig, error: str | None
    ) -> None:
        if self._log is None:
            return
        self._log.record(
            CallRecord(
                run_id=run_id,
                step=step,
                provider=result.provider,
                model=result.model,
                effort=cfg.effort,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                attempts=result.attempts,
                cache_hit=result.cache_hit,
                failover_from=result.failover_from,
                error=error,
            )
        )

    def _record_failure(
        self,
        run_id: str | None,
        step: str,
        ref: str,
        cfg: StepConfig,
        started: float,
        attempts: int,
        usage: _Usage,
        error: str,
    ) -> None:
        """A failed call still cost money for its wasted attempts; the row says how much."""
        if self._log is None:
            return
        provider_name, model = split_model_ref(ref)
        self._log.record(
            CallRecord(
                run_id=run_id,
                step=step,
                provider=provider_name,
                model=model,
                effort=cfg.effort,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
                latency_ms=int((time.perf_counter() - started) * 1000),
                attempts=attempts,
                cache_hit=False,
                error=error,
            )
        )


class BoundLLM:
    """Satisfies the `LLM` contract; every call belongs to `run_id`."""

    def __init__(self, client: LLMClient, run_id: str) -> None:
        self._client = client
        self.run_id = run_id

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        return self._client.call(step, prompt, schema, run_id=self.run_id)

    def input_budget(self, step: str, schema: type[BaseModel]) -> int | None:
        return self._client.input_budget(step, schema)


def _short(exc: Exception, limit: int = 400) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[:limit] + "..."
