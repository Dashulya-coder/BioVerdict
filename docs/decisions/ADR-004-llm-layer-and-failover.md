# ADR-004: One LLM access layer with caching and failover

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

We have consumer subscriptions (which do not include API access), little API budget, free tiers with lower rate limits, and want to switch providers when limits run out. Providers differ in structured-output behavior and in reasoning cost: independent measurements show cost per task depends strongly on reasoning effort, not only on price per token.

## Decision

All model calls go through `llm.call(step, prompt, schema)`:

- model, provider and effort per step from config;
- Pydantic schema validation with retries;
- cache by hash of (model, parameters, prompt);
- failover by error class: 429, quota, 5xx, timeout fail over; auth errors do not;
- a provider circuit breaker for a few minutes after repeated failures;
- logs model, tokens, cost, latency, attempts, real executing model; runs using failover are flagged `mixed_models`;
- per-run budget cap.

One primary provider for the main pipeline, a second as failover, and a third as judge and baseline. The judge is from a different provider than the generator. Failover models are tested on the same documents before use. The live demo uses a fixed model and cached runs.

## Options Considered

| Dimension | A: single provider | B: thin custom layer with failover (chosen) | C: third-party gateway |
|---|---|---|---|
| Resilience | low | medium-high | high |
| Visibility into calls and cost | high | high | lower |
| Build effort | low | low-medium | low |
| Extra dependency | none | none | yes |

## Trade-off Analysis

A gateway saves time but can hide the details we must log. A custom layer is about a hundred lines and keeps full control.

## Consequences

- Easier: surviving limits, measuring cost, swapping models.
- Harder: prompts must work across providers; failover models need testing.
- Revisit if maintenance cost grows.

## Action Items

1. [ ] Implement `llm.call`, error classification, cache, circuit breaker, budget cap.
2. [ ] Tests with a fake provider returning 429, timeout, invalid JSON, empty output.
3. [ ] Run the bake-off in `cost.md` and fix per-step models.
