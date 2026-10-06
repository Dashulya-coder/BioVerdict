# ADR-009: Split the work by pipeline halves, with contracts and fixtures

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** Arsenii, Dasha

## Context

Two people need near-equal workloads and must be able to work in parallel from the first hour. A split into "backend" and "frontend" would leave one side waiting for the other and would make the load uneven (the pipeline logic is much larger than the UI). A split by module would create many cross-dependencies.

## Decision

Split along the seam the architecture already has (ADR-001): the frozen evidence bundle.

- **Arsenii, Track A:** everything before and including the bundle (resolver, connectors, cache, `as_of`, extraction, bundle versions), plus the API, evidence/sources UI, incremental recompute and the eval runner.
- **Dasha, Track B:** everything after the bundle (LLM layer, reasoning modules, scoring, verification, report UI) plus eval cases and sensitivity tests.

Parallelism comes from three things agreed on Day 0: data and function **contracts**, **fixture bundles** built from real documents, and **fakes** (`FakeConnector`, `FakeLLM`) selectable by configuration. The plan is balanced in points per priority tier (see `docs/work-plan.md`) and cuts scope in pairs.

## Options Considered

| Dimension | A: frontend vs backend | B: by module | C: by pipeline half with contracts (chosen) |
|---|---|---|---|
| Balance of workload | poor (UI is smaller) | depends | good, tuned per tier |
| Waiting between people | high | high | low (fixtures and fakes) |
| Integration points | many | many | few (M2, M3) |
| Variety per person | low | medium | high (science, engineering, UI) |
| Risk | one side idle | conflicts | contract drift |

## Trade-off Analysis

C needs a short Day 0 to agree contracts and build fixtures, and it concentrates risk in integration (M2). Contract tests and a pairing session address that.

## Consequences

- Easier: parallel work, clear ownership, scope cuts that keep the balance.
- Harder: contract changes need both approvals; fixtures must be kept in sync with the schema.
- Revisit after M1 and M3 if estimates or skills turn out different.

## Action Items

1. [ ] Complete Phase 0 in `docs/work-plan.md` (contracts, fixtures, fakes, contract tests).
2. [ ] Set the deadline and fill in the capacity check.
3. [ ] Re-estimate after M1 and M3.
