# ADR-007: Time-travel and incremental recompute as first-class features

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

The demo must include an example where new or contradictory evidence changes the conclusion. Judges may check it themselves, so it must be a property of the architecture. We also want to backtest and to show the system does not over-react to weak evidence.

## Decision

- The evidence store is append-only and versioned.
- Every connector and query accepts `as_of`; evidence after that date is excluded.
- Adding evidence creates a new version, classifies the evidence, recomputes only affected claims, re-runs gates and scoring, and emits a diff.
- The diff names which evidence moved which claim through which gate.
- Tests cover three cases: strong counter-evidence flips the verdict; weak counter-evidence only lowers confidence; irrelevant evidence changes nothing.

## Options Considered

| Dimension | A: full re-run on new input | B: incremental recompute (chosen) |
|---|---|---|
| Time in demo | minutes | seconds |
| Explainability | lower | high (diff) |
| Complexity | low | medium |
| Supports backtesting | partly | yes |

## Trade-off Analysis

Incremental recompute needs dependency tracking between claims but makes the demo and the sensitivity tests credible.

## Consequences

- Easier: live evidence input, time-travel demo, sensitivity eval.
- Harder: claims must record `depends_on`; versions must be consistent.
- Risk: time-travel runs can be contaminated by model memory of later events; the quote gate and a leakage count mitigate this.

## Action Items

1. [ ] Implement `as_of` across connectors and store.
2. [ ] Implement the diff and the "add evidence" endpoint.
3. [ ] Add the three sensitivity tests.
