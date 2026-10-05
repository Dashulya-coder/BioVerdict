# ADR-001: Deterministic workflow with a frozen evidence bundle

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO (both team members)

## Context

Free-form deep-research agents produce confident reports whose failures are invisible: valid-looking links with wrong claims, and plausible numbers filled in from model memory when a source is empty. Our task requires traceability, honesty about unknowns and generality. The finals use hidden queries with known expert answers, so predictable behavior matters more than clever search. Unobio has publicly described the same trade-off ("Workflow, Not Agent").

## Decision

Use a fixed DAG with named steps. Split every run into **Collect** (network allowed, through connectors) and **Reason** (no network). Freeze collected documents into a content-hashed bundle. Small tool-calling agents exist only inside Collect nodes, with step limits. LangGraph is used as the DAG runner and for checkpointing only.

## Options Considered

| Dimension | A: single orchestrator agent | B: hybrid DAG + bounded agents (chosen) | C: pure scripted pipeline |
|---|---|---|---|
| Section coverage | not guaranteed | guaranteed | guaranteed |
| Flexible search | high | medium (inside nodes) | low |
| Reproducibility | low | high | highest |
| Grounding enforcement | hard | easy: finite bundle | easy |
| Build effort | low | medium | medium |
| New evidence in demo | full re-run | recompute affected parts | recompute affected parts |

## Trade-off Analysis

B keeps flexible retrieval where it is useful and enforces the closed world where it matters. C would be simpler but too rigid for unfamiliar inputs and sparse assets.

## Consequences

- Easier: grounding checks, reproducible runs, partial failure handling, per-node trace and cost.
- Harder: more engineering than a single agent; a targeted second Collect round must produce bundle v2.
- Revisit if LangGraph hides tracing or cost; then replace it with plain Python functions.

## Action Items

1. [ ] Implement Collect/Freeze/Reason boundary and a test that reasoning code imports no network client.
2. [ ] Implement bundle hashing and source catalog.
3. [ ] Implement targeted second round (max 2-3).
