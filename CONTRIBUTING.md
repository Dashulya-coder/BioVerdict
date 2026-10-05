# Contributing / team workflow

Two-person team. The rules exist to avoid blocking each other, not to add ceremony.

## Roles

| Role | Owner | Scope |
|---|---|---|
| A: data and verdict | TODO | Connectors, evidence store with versions and `as_of`, verifier, scoring, eval |
| B: analysis and product | TODO | Resolver, LangGraph DAG, agents and prompts, Bull/Bear/Chair, API, UI, diligence questions |
| Both | | Data schema, ADRs, demo, README |

Each module has one owner. The other person reviews.

## Schema changes (the expensive kind)

`docs/data-model.md` is the contract between our halves.

1. Propose the change in a PR that edits `data-model.md` first.
2. Both approve before code changes.
3. Bump `schema_version` and add a migration if the SQLite schema changes.

## Git

- `main` is always runnable. Changes go through a pull request reviewed by the other person.
- Branches: `feat/<area>-<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
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

- Short daily sync: what is blocked, what changes in the schema, what is risky.
- Code freeze for the demo: TODO date and time. After it only bug fixes and docs.

## Decisions

Non-trivial decisions get an ADR in `docs/decisions/` (copy the existing format). Status starts as `Proposed` and becomes `Accepted` when both agree.
