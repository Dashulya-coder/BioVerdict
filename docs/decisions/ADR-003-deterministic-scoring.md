# ADR-003: Deterministic scoring; the LLM classifies only

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

Language models tend toward optimism, give different answers across runs, and invent numbers. We need reproducible verdicts, explainable changes when evidence arrives, and probabilities and valuations with visible assumptions.

## Decision

Code computes: claim confidence, gates, probability of success, rNPV (Monte Carlo, P10/P50/P90), capital and time to milestone, and the verdict. The LLM only extracts and classifies (evidence level, stance, affected claims) and writes prose from computed results. All weights and thresholds live in `config/scoring.yaml` and are calibrated on the eval set with logged reasons.

## Options Considered

| Dimension | A: LLM judges the verdict | B: code scores, LLM classifies (chosen) | C: trained model |
|---|---|---|---|
| Reproducibility | low | high | high |
| Explainability of changes | low | high | low |
| Data needed | none | benchmarks and small eval set | large labelled set (unavailable) |
| Optimism bias | high | controlled by gates and thresholds | unknown |

## Trade-off Analysis

B gives the transparency and testability the task asks for with data we can obtain. C is infeasible without ground truth.

## Consequences

- Easier: explaining and testing verdict changes; sensitivity analysis; regression tests.
- Harder: we must source and justify priors; weights start as heuristics and need calibration.
- Revisit if calibration shows systematic bias.

## Action Items

1. [ ] Implement gates, confidence, PoS, rNPV, capital with unit tests.
2. [ ] Test: weak in vitro contradiction does not flip a claim backed by human genetics; strong clinical contradiction does.
3. [ ] Calibrate thresholds after the first eval run.
