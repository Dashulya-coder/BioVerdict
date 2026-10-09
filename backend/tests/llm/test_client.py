import pytest
from pydantic import BaseModel, ValidationError

from bioverdict.contracts import LLM
from bioverdict.llm import (
    AllModelsFailedError,
    BudgetExceededError,
    ConfigError,
    FakeLLM,
    FatalProviderError,
    InvalidOutputError,
    LLMClient,
    LLMConfig,
    RefusalError,
    RunTimeoutError,
    StepConfig,
    TransientProviderError,
)
from bioverdict.llm.breaker import CircuitBreaker
from bioverdict.llm.budget import Deadline
from bioverdict.llm.cache import DiskCache, MemoryCache
from bioverdict.llm.call_log import MemoryCallLog, SqliteCallLog
from bioverdict.llm.config import DEFAULT_PRICES, HAIKU, OPUS, SONNET
from bioverdict.llm.providers.fake import FakeProvider
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate

GOOD = '{"verdict": "ok", "score": 3}'


class Answer(BaseModel):
    verdict: str
    score: int


def config(*models: str, **kw) -> LLMConfig:
    step = StepConfig(models=list(models), **kw.pop("step", {}))
    return LLMConfig(steps={"s": step}, prices=dict(DEFAULT_PRICES), **kw)


def client(cfg: LLMConfig, **providers: FakeProvider) -> LLMClient:
    return LLMClient(cfg, providers, cache=MemoryCache(), call_log=MemoryCallLog())


def anthropic_only(*outcomes) -> tuple[LLMClient, FakeProvider]:
    fake = FakeProvider(*outcomes, name="anthropic")
    return client(config(HAIKU), anthropic=fake), fake


def test_happy_path_returns_validated_result_with_cost() -> None:
    llm, _ = anthropic_only(GOOD)
    result = llm.call("s", "prompt", Answer, run_id="R1")
    assert result.parsed == {"verdict": "ok", "score": 3}
    assert (result.provider, result.model, result.attempts) == ("anthropic", "claude-haiku-4-5", 1)
    assert result.cost_usd == pytest.approx((100 * 1.0 + 50 * 5.0) / 1_000_000)
    assert llm.spent("R1") == pytest.approx(result.cost_usd)


def test_invalid_json_is_retried_with_feedback_on_the_same_model() -> None:
    llm, fake = anthropic_only("not json", GOOD)
    result = llm.call("s", "the prompt", Answer)
    assert result.attempts == 2
    assert "rejected" in fake.requests[1].prompt and "the prompt" in fake.requests[1].prompt


def test_empty_output_counts_as_invalid() -> None:
    llm, _ = anthropic_only("", "{}", GOOD)
    assert llm.call("s", "p", Answer).attempts == 3


def test_persistent_invalid_output_fails_over_then_gives_up() -> None:
    llm, fake = anthropic_only("nope")
    with pytest.raises(AllModelsFailedError) as info:
        llm.call("s", "p", Answer)
    assert len(fake.requests) == 3  # one try + two validation retries
    assert "InvalidOutputError" in str(info.value)


def test_rate_limit_fails_over_to_the_next_model() -> None:
    cfg = config(HAIKU, SONNET)
    fake = FakeProvider(TransientProviderError("429", "rate_limit"), GOOD, name="anthropic")
    result = client(cfg, anthropic=fake).call("s", "p", Answer, run_id="R")
    assert result.model == "claude-sonnet-5-5"
    assert result.failover_from == HAIKU


def test_timeout_fails_over_across_providers() -> None:
    cfg = config(HAIKU, "other:model-x")
    cfg.prices["other:model-x"] = DEFAULT_PRICES[HAIKU]
    primary = FakeProvider(TransientProviderError("slow", "timeout"), name="anthropic")
    backup = FakeProvider(GOOD, name="other")
    llm = client(cfg, anthropic=primary, other=backup)
    result = llm.call("s", "p", Answer, run_id="R")
    assert result.provider == "other"
    assert llm.mixed_models("R") and not llm.mixed_models("elsewhere")


def test_auth_errors_do_not_fail_over() -> None:
    cfg = config(HAIKU, SONNET)
    fake = FakeProvider(FatalProviderError("401 bad key"), GOOD, name="anthropic")
    with pytest.raises(FatalProviderError):
        client(cfg, anthropic=fake).call("s", "p", Answer)
    assert len(fake.requests) == 1


def test_refusal_fails_over_without_hurting_the_breaker() -> None:
    cfg = config(HAIKU, SONNET)
    fake = FakeProvider(RefusalError("declined"), GOOD, name="anthropic")
    llm = LLMClient(cfg, {"anthropic": fake}, breaker=CircuitBreaker(threshold=1))
    assert llm.call("s", "p", Answer).failover_from == HAIKU
    assert llm.call("s", "other prompt", Answer)  # the provider is still callable


def test_all_models_failing_is_reported_with_every_reason() -> None:
    cfg = config(HAIKU, SONNET)
    fake = FakeProvider(TransientProviderError("down", "server"), name="anthropic")
    with pytest.raises(AllModelsFailedError) as info:
        client(cfg, anthropic=fake).call("s", "p", Answer)
    assert len(info.value.attempts) == 2


def test_circuit_breaker_opens_then_recovers_after_cooldown() -> None:
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown_s=60, clock=lambda: now[0])
    fake = FakeProvider(
        TransientProviderError("x", "server"),
        TransientProviderError("x", "server"),
        GOOD,
        name="anthropic",
    )
    llm = LLMClient(config(HAIKU), {"anthropic": fake}, breaker=breaker)
    for text in ("a", "b"):
        with pytest.raises(AllModelsFailedError):
            llm.call("s", text, Answer)
    with pytest.raises(AllModelsFailedError) as info:
        llm.call("s", "c", Answer)
    assert "breaker open" in str(info.value) and len(fake.requests) == 2  # not even tried
    now[0] = 61
    assert llm.call("s", "d", Answer).parsed["score"] == 3


def test_budget_cap_stops_further_calls() -> None:
    llm = client(config(HAIKU, budget_usd=0.0002), anthropic=FakeProvider(GOOD, name="anthropic"))
    llm.call("s", "first", Answer, run_id="R")  # costs 0.00035 > cap
    with pytest.raises(BudgetExceededError):
        llm.call("s", "second", Answer, run_id="R")
    assert llm.call("s", "other run", Answer, run_id="R2")  # budgets are per run


def test_cache_returns_the_same_answer_without_calling_or_paying() -> None:
    llm, fake = anthropic_only(GOOD)
    first = llm.call("s", "same", Answer, run_id="R")
    second = llm.call("s", "same", Answer, run_id="R")
    assert len(fake.requests) == 1
    assert second.cache_hit and second.cost_usd == 0.0 and second.parsed == first.parsed
    assert llm.spent("R") == pytest.approx(first.cost_usd)
    assert not llm.call("s", "different", Answer).cache_hit


def test_disk_cache_survives_a_new_client(tmp_path) -> None:
    cfg = config(HAIKU)
    fake = FakeProvider(GOOD, name="anthropic")
    LLMClient(cfg, {"anthropic": fake}, cache=DiskCache(tmp_path)).call("s", "p", Answer)
    again = FakeProvider(GOOD, name="anthropic")
    hit = LLMClient(cfg, {"anthropic": again}, cache=DiskCache(tmp_path)).call("s", "p", Answer)
    assert hit.cache_hit and not again.requests


def test_cache_key_covers_parameters() -> None:
    a = client(
        config(HAIKU, step={"effort": "low"}), anthropic=FakeProvider(GOOD, name="anthropic")
    )
    shared = MemoryCache()
    a._cache = shared
    a.call("s", "p", Answer)
    b = client(
        config(HAIKU, step={"effort": "high"}), anthropic=FakeProvider(GOOD, name="anthropic")
    )
    b._cache = shared
    assert not b.call("s", "p", Answer).cache_hit


def test_every_call_is_logged_including_cache_hits_and_failures() -> None:
    log = MemoryCallLog()
    fake = FakeProvider(GOOD, name="anthropic")
    llm = LLMClient(config(HAIKU), {"anthropic": fake}, cache=MemoryCache(), call_log=log)
    llm.call("s", "p", Answer, run_id="R")
    llm.call("s", "p", Answer, run_id="R")
    assert [e.cache_hit for e in log.entries] == [False, True]
    bad = FakeProvider(TransientProviderError("down", "server"), name="anthropic")
    failing = LLMClient(config(HAIKU), {"anthropic": bad}, call_log=log)
    with pytest.raises(AllModelsFailedError):
        failing.call("s", "p", Answer, run_id="R")
    assert log.entries[-1].error and log.entries[-1].cost_usd == 0.0


def test_sqlite_log_writes_to_llm_calls(tmp_path) -> None:
    db = tmp_path / "t.db"
    migrate(connect(db))
    llm = LLMClient(
        config(HAIKU),
        {"anthropic": FakeProvider(GOOD, name="anthropic")},
        call_log=SqliteCallLog(db),
    )
    llm.call("s", "p", Answer, run_id="R1")
    row = connect(db).execute("SELECT * FROM llm_calls").fetchone()
    assert (row["run_id"], row["step"], row["model"], row["cache_hit"]) == (
        "R1",
        "s",
        "claude-haiku-4-5",
        0,
    )
    assert row["cost_usd"] > 0 and row["input_tokens"] == 100


def test_configuration_errors_are_loud() -> None:
    llm = client(config(HAIKU), anthropic=FakeProvider(GOOD, name="anthropic"))
    with pytest.raises(ConfigError):
        llm.call("unknown-step", "p", Answer)
    with pytest.raises(ConfigError):
        client(config(HAIKU, "other:m"), anthropic=FakeProvider(GOOD, name="anthropic"))
    with pytest.raises(ConfigError):  # a model without a price cannot be budgeted
        LLMConfig(steps={"s": StepConfig(models=["x:y"])}, prices={}).validate_prices()


def test_default_config_is_priced_and_complete() -> None:
    cfg = LLMConfig.default()
    assert {"resolver", "extraction", "reasoning", "skeptic", "chair", "synthesis"} <= set(
        cfg.steps
    )
    assert cfg.step("extraction").models == [HAIKU]


def test_fake_llm_satisfies_the_contract_and_validates_answers() -> None:
    fake = FakeLLM({"s": Answer(verdict="v", score=1), "bad": {"verdict": "v"}})
    assert isinstance(fake, LLM)
    assert fake.call("s", "p", Answer).parsed == {"verdict": "v", "score": 1}
    with pytest.raises(ValidationError):
        fake.call("bad", "p", Answer)
    with pytest.raises(KeyError):
        fake.call("missing", "p", Answer)


def test_bound_client_satisfies_the_contract_and_carries_the_run_id() -> None:
    log = MemoryCallLog()
    llm = LLMClient(
        config(HAIKU), {"anthropic": FakeProvider(GOOD, name="anthropic")}, call_log=log
    )
    bound = llm.bind("R9")
    assert isinstance(bound, LLM)
    result = bound.call("s", "p", Answer)  # the plain three-argument contract
    assert log.entries[0].run_id == "R9"
    assert llm.spent("R9") == pytest.approx(result.cost_usd) and llm.spent(None) == 0.0


# --- review fixes ------------------------------------------------------------


def test_cost_covers_every_attempt_not_just_the_last() -> None:
    """Reproduced by review: a retry after invalid JSON used to report half of what was spent."""
    llm, _ = anthropic_only("not json", GOOD)
    result = llm.call("s", "p", Answer, run_id="R")
    one_attempt = (100 * 1.0 + 50 * 5.0) / 1_000_000
    assert result.attempts == 2
    assert result.cost_usd == pytest.approx(2 * one_attempt)
    assert (result.input_tokens, result.output_tokens) == (200, 100)
    assert result.cost_usd == pytest.approx(llm.spent("R"))  # result and budget agree


def test_cost_of_a_model_that_failed_before_the_failover_is_kept() -> None:
    cfg = config(HAIKU, SONNET)
    fake = FakeProvider("nope", "nope", "nope", GOOD, name="anthropic")  # haiku wastes 3 tries
    log = MemoryCallLog()
    llm = LLMClient(cfg, {"anthropic": fake}, call_log=log)
    result = llm.call("s", "p", Answer, run_id="R")
    haiku_try = (100 * 1.0 + 50 * 5.0) / 1_000_000
    sonnet_try = (100 * 2.0 + 50 * 10.0) / 1_000_000
    assert result.cost_usd == pytest.approx(3 * haiku_try + sonnet_try)
    assert result.cost_usd == pytest.approx(llm.spent("R"))
    assert log.entries[0].cost_usd == pytest.approx(result.cost_usd)


def test_a_failed_call_logs_the_money_its_wasted_attempts_cost() -> None:
    log = MemoryCallLog()
    llm = LLMClient(
        config(HAIKU), {"anthropic": FakeProvider("nope", name="anthropic")}, call_log=log
    )
    with pytest.raises(AllModelsFailedError):
        llm.call("s", "p", Answer, run_id="R")
    assert log.entries[0].error
    assert log.entries[0].cost_usd > 0
    assert log.entries[0].cost_usd == pytest.approx(llm.spent("R"))


def test_a_cache_hit_of_a_failover_answer_still_flags_mixed_models() -> None:
    cfg = config(HAIKU, SONNET)
    cache = MemoryCache()
    first = FakeProvider(TransientProviderError("429", "rate_limit"), GOOD, name="anthropic")
    LLMClient(cfg, {"anthropic": first}, cache=cache).call("s", "p", Answer, run_id="A")
    replay = LLMClient(cfg, {"anthropic": FakeProvider(GOOD, name="anthropic")}, cache=cache)
    assert replay.call("s", "p", Answer, run_id="B").cache_hit
    assert replay.mixed_models("B")


def test_the_run_deadline_stops_further_calls_and_caps_each_timeout() -> None:
    now = [0.0]
    deadline = Deadline(limit_s=100, clock=lambda: now[0])
    fake = FakeProvider(GOOD, name="anthropic")
    llm = LLMClient(config(HAIKU, step={"timeout_s": 90.0}), {"anthropic": fake}, deadline=deadline)
    llm.call("s", "first", Answer, run_id="R")
    now[0] = 60.0  # 40 s left: the step allows 90 s but the run only has 40
    llm.call("s", "second", Answer, run_id="R")
    assert fake.requests[1].timeout_s == pytest.approx(40.0)
    now[0] = 101.0
    with pytest.raises(RunTimeoutError):
        llm.call("s", "third", Answer, run_id="R")
    assert len(fake.requests) == 2  # nothing was sent after the deadline
    assert llm.call("s", "other run", Answer, run_id="R2")  # each run has its own clock


def test_the_default_config_gives_reasoning_a_second_model_and_more_time() -> None:
    cfg = LLMConfig.default()
    assert cfg.step("reasoning").models == [SONNET, OPUS]
    assert cfg.step("synthesis").timeout_s > cfg.step("extraction").timeout_s == 90.0
    assert cfg.run_timeout_s == 420.0


# --- an unusable answer is still paid for ------------------------------------------------


def test_the_budget_and_the_log_see_the_tokens_of_a_failed_answer() -> None:
    """Reproduced by the review of #51: a cut-off answer (1000 in, 4000 out) was recorded as $0."""
    from bioverdict.llm.errors import FatalProviderError

    cutoff = FatalProviderError("answer cut off at max_tokens").with_usage(1000, 4000)
    log = MemoryCallLog()
    llm = LLMClient(
        config(HAIKU), {"anthropic": FakeProvider(cutoff, name="anthropic")}, call_log=log
    )
    with pytest.raises(FatalProviderError):
        llm.call("s", "p", Answer, run_id="R")
    billed = (1000 * 1.0 + 4000 * 5.0) / 1_000_000
    assert llm.spent("R") == pytest.approx(billed)
    assert log.entries[0].cost_usd == pytest.approx(billed)
    assert (log.entries[0].input_tokens, log.entries[0].output_tokens) == (1000, 4000)


def test_a_refusal_before_a_failover_is_charged_and_counted_in_the_result() -> None:
    refusal = RefusalError("declined (category: bio)").with_usage(500, 20)
    fake = FakeProvider(refusal, GOOD, name="anthropic")
    llm = LLMClient(config(HAIKU, SONNET), {"anthropic": fake})
    result = llm.call("s", "p", Answer, run_id="R")
    wasted = (500 * 1.0 + 20 * 5.0) / 1_000_000
    good = (100 * 2.0 + 50 * 10.0) / 1_000_000
    assert result.cost_usd == pytest.approx(wasted + good)
    assert result.cost_usd == pytest.approx(llm.spent("R"))


def test_unreadable_json_from_the_provider_is_charged_for_each_attempt() -> None:
    bad = InvalidOutputError("not json").with_usage(200, 300)
    fake = FakeProvider(bad, bad, GOOD, name="anthropic")
    llm = LLMClient(config(HAIKU), {"anthropic": fake})
    result = llm.call("s", "p", Answer, run_id="R")
    spent = 2 * (200 * 1.0 + 300 * 5.0) / 1_000_000 + (100 * 1.0 + 50 * 5.0) / 1_000_000
    assert result.cost_usd == pytest.approx(spent) == pytest.approx(llm.spent("R"))


def test_an_error_without_usage_charges_nothing() -> None:
    llm = LLMClient(
        config(HAIKU),
        {"anthropic": FakeProvider(TransientProviderError("429", "rate_limit"), name="anthropic")},
    )
    with pytest.raises(AllModelsFailedError):
        llm.call("s", "p", Answer, run_id="R")
    assert llm.spent("R") == 0.0


def test_a_cut_off_answer_is_retried_with_a_request_to_write_less() -> None:
    from bioverdict.llm.errors import OutputTruncatedError

    class CutOffOnce(FakeProvider):
        def complete(self, request):
            if len(self.requests) == 0:
                self.requests.append(request)
                raise OutputTruncatedError("answer cut off").with_usage(10, 4096)
            return super().complete(request)

    provider = CutOffOnce('{"verdict": "ok", "score": 1}', name="anthropic")
    client = LLMClient(LLMConfig.default(), {"anthropic": provider})
    client.call("reasoning.clinical", "prompt", Answer)
    assert "cut off because it was too long" in provider.requests[-1].prompt
