# ADR-005: SQLite and file cache; no Redis

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

Two developers, a hackathon time frame, and a need for versioned evidence, run history, HTTP and LLM caches, and traces. Runs take minutes, so request handlers must not block.

## Decision

Use SQLite in WAL mode for runs, bundles, evidence, claims, links, LLM calls, HTTP cache and verification log. Run jobs in the FastAPI process (background tasks or asyncio) with job state in SQLite; stream progress with SSE. No Redis, no Celery. Each developer has a local database; demo state is shared as a dump.

## Options Considered

| Dimension | A: SQLite (chosen) | B: Postgres + Redis |
|---|---|---|
| Setup | trivial | docker services |
| Concurrency | single writer, enough for us | high |
| Failure surface in demo | low | higher |
| Ops effort | none | some |

## Trade-off Analysis

We do not need pub/sub, queues or multiple workers. Fewer moving parts means fewer demo failures. AACT can be queried through its public interface or added later if needed.

## Consequences

- Easier: setup, backup, replay of demo runs.
- Harder: no horizontal scaling; do not share one DB file across machines.
- Revisit if concurrency or data size grows.

## Action Items

1. [ ] Create schema and migrations (`schema_version`).
2. [ ] Enable WAL; test concurrent reads during a run.
3. [ ] Implement job state and SSE.
