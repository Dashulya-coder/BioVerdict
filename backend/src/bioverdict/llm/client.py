"""`llm.call(step, prompt, schema)`: the only way code talks to a model (ADR-004).

Order of events for one call: cache lookup, then the step's model chain. Per model: budget check,
provider call, schema validation (invalid JSON is retried on the same model with feedback).
Transient errors (429, quota, 5xx, timeout) fail over to the next model and count against the
provider's circuit breaker; auth and bad-request errors do not fail over.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from bioverdict.llm.breaker import CircuitBreaker
from bioverdict.llm.budget import Budget
from bioverdict.llm.cache import LLMCache, cache_key
from bioverdict.llm.call_log import CallLog, CallRecord
from bioverdict.llm.config import LLMConfig, StepConfig
from bioverdict.llm.errors import (
    AllModelsFailedError,
    BudgetExceededError,
    ConfigError,
    FatalProviderError,
    InvalidOutputError,
    RefusalError,
    TransientProviderError,
)
from bioverdict.llm.types import Provider, ProviderRequest, ProviderResponse, split_model_ref
from bioverdict.store.models import LLMResult


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

        def request_for(ref: str, text: str) -> ProviderRequest:
            return ProviderRequest(
                model=split_model_ref(ref)[1],
                prompt=text,
                schema=schema,
                system=system,
                effort=cfg.effort,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout_s=cfg.timeout_s,
            )

        primary = cfg.models[0]
        key = cache_key(primary, request_for(primary, prompt))
        hit = self._cache_lookup(key, schema)
        if hit is not None:
            result = hit.model_copy(
                update={
                    "step": step,
                    "cache_hit": True,
                    "cost_usd": 0.0,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            self._record(run_id, step, result, cfg, error=None)
            return result

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
                response, used = self._ask_model(ref, cfg, prompt, request_for, schema, run_id)
            except (TransientProviderError, RefusalError, InvalidOutputError) as exc:
                attempts += getattr(exc, "attempts", 1)
                failures.append(f"{ref}: {type(exc).__name__}: {exc}")
                first_failed = first_failed or ref
                if isinstance(exc, TransientProviderError):
                    self._breaker.record_failure(provider_name)
                continue
            except (FatalProviderError, BudgetExceededError) as exc:
                self._record_failure(run_id, step, ref, cfg, started, attempts + 1, str(exc))
                raise
            attempts += used
            self._breaker.record_success(provider_name)
            result = self._build_result(
                step, ref, response, schema, started, attempts, first_failed, run_id
            )
            if self._cache is not None:
                self._cache.put(key, result.model_dump(mode="json"))
            self._record(run_id, step, result, cfg, error=None)
            return result

        error = AllModelsFailedError(step, failures)
        self._record_failure(run_id, step, primary, cfg, started, attempts, str(error))
        raise error

    def mixed_models(self, run_id: str | None) -> bool:
        """True when any call of the run was answered by a failover model (flag for the trace)."""
        with self._lock:
            return (run_id or "-") in self._mixed

    def spent(self, run_id: str | None) -> float:
        return self._budget.spent(run_id)

    # -- internals ------------------------------------------------------------

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
        request_for,
        schema: type[BaseModel],
        run_id: str | None,
    ) -> tuple[ProviderResponse, int]:
        """Call one model, retrying invalid JSON with feedback. Returns (response, attempts)."""
        provider = self._providers[split_model_ref(ref)[0]]
        text = prompt
        last: InvalidOutputError | None = None
        for attempt in range(1, cfg.max_validation_retries + 2):
            self._budget.check(run_id)
            try:
                response = provider.complete(request_for(ref, text))
                self._charge(run_id, ref, response)
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

    def _charge(self, run_id: str | None, ref: str, response: ProviderResponse) -> None:
        self._budget.charge(run_id, self._cost(ref, response))

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
    ) -> LLMResult:
        provider_name, _ = split_model_ref(ref)
        if first_failed is not None:
            with self._lock:
                self._mixed.add(run_id or "-")
        return LLMResult(
            step=step,
            provider=provider_name,
            model=response.model,
            parsed=schema.model_validate_json(response.text).model_dump(mode="json"),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=self._cost(ref, response),
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
        error: str,
    ) -> None:
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
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                attempts=attempts,
                cache_hit=False,
                error=error,
            )
        )


def _short(exc: Exception, limit: int = 400) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[:limit] + "..."
