# ADR-002: Claim ledger with basis labels and section statuses

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

The task demands explicit separation of source evidence from AI inference, and honesty about missing information. A two-way label (`source_fact` / `ai_inference`) hides important differences: a calculated number, a modeled valuation and an unsupported hypothesis are different things. An empty cell can mean four different situations.

## Decision

Every claim has a `basis`: `extracted`, `derived`, `inferred`, `modeled`, `hypothesis`, `unknown`. Every report section has a `status`: `found`, `conflicting`, `not_reported`, `none_found`, `not_searched`, `error`, `incomplete`. Stance (supports/contradicts/neutral) is stored on the claim-evidence link, not on the evidence. Each quoted claim carries a verbatim quote verified against the bundle.

## Options Considered

| Dimension | A: two labels | B: six labels + statuses (chosen) |
|---|---|---|
| Expressiveness | low | high |
| UI complexity | low | medium |
| Fit with verdict code | weak | strong (`modeled` feeds rNPV) |
| Risk of valuation passing as fact | high | low |

## Trade-off Analysis

B costs a little UI and prompt complexity but makes unknowns actionable and keeps valuation visibly an assumption.

## Consequences

- Easier: drill-down with meaningful badges, diligence questions with data types, honest sparse-asset reports.
- Harder: prompts and verifiers must handle more states.
- Maps to the original two labels: `extracted`/`derived` are source-based; `inferred`/`modeled`/`hypothesis` are AI inference.

## Action Items

1. [ ] Add `basis`, `status`, link-level `direction` to the schema.
2. [ ] UI badges for each basis.
3. [ ] Tests: unverified claim becomes `inferred` with capped confidence.
