# Contributing / team workflow

Two-person team (Arsenii and Dasha). The rules exist to avoid blocking each other, not to add ceremony.

## Roles

The full split, task lists, estimates and milestones are in [`docs/work-plan.md`](docs/work-plan.md). Summary:

| Person | Track | Scope |
|---|---|---|
| **Arsenii** | A: Evidence and platform | Resolver, connectors, cache and `as_of`, bundle freeze and versions, extraction agents, all API routers, incremental recompute and diff, evidence/sources UI and app shell, eval runner, ops (runbook, cost measurement, demo recordings) |
| **Dasha** | B: Reasoning and verdict | `llm.call` layer, reasoning modules, Skeptic/Chair, scoring, rNPV and capital, verification, report UI and translation-chain graph, trace/cost panel, eval cases and sensitivity tests, domain pack |
| Both | | Contracts (data model, `contracts.py`), ADRs, fixtures, integration milestones, demo, README |

Each directory has one owner (ownership map in `docs/work-plan.md`). The other person reviews. The workload is balanced at about 47 and 46 points; rebalance as described in the work plan if estimates change.

## Schema changes (the expensive kind)

`docs/data-model.md` is the contract between our halves.

1. Propose the change in a PR that edits `data-model.md` first.
2. Both approve before code changes.
3. Bump `schema_version` and add a migration if the SQLite schema changes.

## Git

- `main` is always runnable. Changes go through a pull request reviewed by the other person.
- Branches: `arsenii/<task-id>-<short-name>` and `dasha/<task-id>-<short-name>` (task IDs from `docs/work-plan.md`, for example `dasha/B4-scoring-gates`).
- Commits follow Conventional Commits: `feat(verify): reject quotes absent from bundle`.
- Keep PRs small (under about 400 changed lines). Large PRs wait for review.

## Definition of done

A change is done when:

- tests pass, and verifier and scoring changes include tests;
- no network call exists in the reasoning phase;
- new LLM calls go through `llm.call` and appear in the trace;
- no secrets in the diff;
- docs are updated if a contract changed.

## Rules that must not be broken

1. LLM output never writes a URL, PMID or NCT ID that did not come from retrieval.
2. LLM output never produces a number that the verdict depends on. Code computes it.
3. Reasoning code never imports a network client.
4. A claim that fails verification is dropped, not softened.

## Secrets

Keys live in `.env` (git-ignored). Each developer has their own keys. Never paste keys into issues, PRs or chat.

## Sync

- Short daily sync (10 minutes): what I finished, what I start, what could block you. Update the status column in `docs/work-plan.md`.
- At most two tasks in progress per person.
- Pairing sessions at milestones M2 (bundle handoff) and M4 (eval and calibration).
- Code freeze for the demo: TODO date and time. After it only bug fixes and docs.

## Decisions

Non-trivial decisions get an ADR in `docs/decisions/` (copy the existing format). Status starts as `Proposed` and becomes `Accepted` when both agree.
