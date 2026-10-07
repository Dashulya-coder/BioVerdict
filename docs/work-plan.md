# Work plan and role split

Two people, one goal: **near-equal workload, and both of us busy from the first hour.** This document is the source of truth for who does what. Ownership lives here and in `CONTRIBUTING.md`.

| Person | Track | Mission |
|---|---|---|
| **Arsenii** | **A: Evidence and platform** | Everything from the question to a frozen, versioned evidence bundle; the API; the evidence and sources UI; incremental recompute; the eval harness |
| **Dasha** | **B: Reasoning and verdict** | Everything from the frozen bundle to the verdict: LLM layer, reasoning modules, scoring, verification, report UI, eval cases |

## What this plan satisfies

1. **Equal work.** 47 points for Arsenii, 46 for Dasha (table below). The split is balanced inside every priority tier, so cutting scope keeps it balanced.
2. **Parallel from hour one.** The tracks meet only at the frozen bundle. Agreed contracts, fixture bundles and fake implementations let each person run the whole pipeline without waiting for the other (section 3).
3. **Variety for both.** Each track has science-heavy work, engineering work and UI work.
4. **Clear ownership.** Every directory has one owner (section 8). Cross-track changes go through the other person's review.
5. **Swappable.** Skill levels were not stated. If either person prefers the other track, swap the whole tracks (names in this file, `CONTRIBUTING.md`, `README.md`); the contracts make the tracks interchangeable.

## 1. Sizing

1 point is roughly half a working day for one person. **That is a rough guess, not a measurement.** Re-estimate after the first two tasks and update the table. The deadline was not provided, so the plan is expressed in points and priorities, not calendar days (see section 9).

| Priority | Arsenii | Dasha |
|---|---|---|
| P0 | 21 | 22 |
| P1 | 17 | 16 |
| P2 | 6 | 5 |
| P3 | 3 | 3 |
| **Total** | **47** | **46** |

Priorities: **P0** minimum for an end-to-end verdict with drill-down; **P1** needed for the strongest demo and for evaluation; **P2** polish and breadth; **P3** if time remains. "Demo-critical" marks tasks the finals depend on.

## 2. Task lists

### Arsenii: Track A (Evidence and platform)

| ID | Task | Priority | Points | Demo-critical | Status |
|---|---|---|---|---|---|
| A1 | Resolver: input formats (indication+mechanism, drug name, company code) to MONDO/EFO, UniProt/Ensembl, ChEMBL/Open Targets IDs; alias disambiguation | P0 | 3 | yes | [x] |
| A2 | Connectors: ClinicalTrials.gov v2 and Open Targets, returning `Evidence` objects | P0 | 4 | yes | [ ] |
| A3 | HTTP cache, `as_of` filter, source catalog (allowlist), bundle freeze, hash and versions | P0 | 3 | yes | [x] |
| A4 | Extraction collect agents: quote + value into `Evidence`, section statuses, bounded tool loops | P0 | 4 | yes | [ ] |
| A5 | API routes: report, claims, evidence, trace, SSE (stable contract); UI shell, input and resolver screen, evidence/source explorer | P0 | 7 | yes | [ ] |
| A6 | Connectors: PubMed / Europe PMC and openFDA / Drugs@FDA | P1 | 4 |  | [ ] |
| A7 | Incremental recompute engine, add-evidence endpoint, diff API and diff screen | P1 | 5 | yes | [ ] |
| A8 | Eval runner, grounding and citation metrics, leakage probe, cache pre-warm | P1 | 4 |  | [ ] |
| A9 | Epidemiology and pricing connectors (SEER, GCO, CMS) and TAM numbers derived by code | P1 | 4 |  | [ ] |
| A10 | Connectors: SEC EDGAR and Tavily | P2 | 3 |  | [ ] |
| A11 | Ops: runbook upkeep, cost measurement from the trace table, model bake-off run, demo recordings | P2 | 3 |  | [ ] |
| A12 | Patent/IP connectors (Google Patents links, Orange/Purple Book) and market-sentiment module | P3 | 3 |  | [ ] |

Status notes (2026-10-07): A1 (PR #30) and A3 are done. A2: ClinicalTrials.gov and Open Targets are done; posted results (`hasResults`) and pagination of ClinicalTrials.gov remain. A5: the backend API runs on fixtures (`docs/architecture.md` section 12); the UI shell and the evidence screens remain.

### Dasha: Track B (Reasoning and verdict)

| ID | Task | Priority | Points | Demo-critical | Status |
|---|---|---|---|---|---|
| B1 | LLM layer: `llm.call`, provider adapters, schema validation and retries, cache, failover, circuit breaker, budget cap, logging | P0 | 5 | yes | [ ] |
| B2 | Reasoning modules: mechanism validation and translation chain (supported / weak / missing links) | P0 | 5 | yes | [ ] |
| B3 | Reasoning modules: clinical development and competition and pipeline | P0 | 4 | yes | [ ] |
| B4 | Scoring: gates, claim confidence, probability of success, verdict mapping | P0 | 4 | yes | [ ] |
| B5 | Report UI: executive verdict, claim drill-down, translation-chain graph | P0 | 4 | yes | [ ] |
| B6 | Reasoning modules: disease and unmet need; commercial opportunity (uses TAM numbers from A9) | P1 | 3 |  | [ ] |
| B7 | rNPV Monte Carlo, capital and time to milestone, tornado chart | P1 | 3 |  | [ ] |
| B8 | Verification: entailment judge (other provider), source authority, temporal validity | P1 | 3 | yes | [ ] |
| B9 | Skeptic and Chair steps; diligence questions ranked by value of information | P1 | 3 |  | [ ] |
| B10 | Eval set: cases and expectations, sensitivity tests (strong, weak, noise), baselines | P1 | 4 | yes | [ ] |
| B11 | Domain pack (oncology), docs content: sources, limitations, results, demo script | P2 | 3 |  | [ ] |
| B12 | Trace and cost panel, progress UI | P2 | 2 |  | [ ] |
| B13 | Reasoning modules: IP/regulatory and red/green flags | P3 | 3 |  | [ ] |

## 3. Why the tracks run in parallel

The pipeline has a natural seam (ADR-001, ADR-009): everything before the frozen bundle collects evidence; everything after reasons over it. Three mechanisms remove the waiting:

1. **Contracts first.** The data models (`docs/data-model.md`, `bioverdict/store/models.py`) and a small set of function signatures (below) are agreed on Day 0 and then change only by joint approval.
2. **Fixture bundles.** Hand-built bundles from real documents (for example a divarasib bundle and an HRO761 bundle) let Dasha develop reasoning, scoring and verification before any connector exists, and let Arsenii test connectors against a known-good shape.
3. **Fakes behind flags.** `FakeConnector` (reads fixtures) and `FakeLLM` (canned answers per step) let either person run the whole DAG from day one. Real implementations replace the fakes through configuration (`USE_FIXTURES=1`), so integration is a switch, not a rewrite.

Contracts (Python protocols in `bioverdict/contracts.py`):

| Contract | Signature (sketch) | Producer | Consumer |
|---|---|---|---|
| Connector | `async fetch(query, as_of) -> list[Evidence]` | Arsenii | Arsenii (collect nodes) |
| Bundle | frozen `Bundle` + `Evidence` list, content hash, catalog | Arsenii | Dasha |
| LLM | `llm.call(step, prompt, schema) -> LLMResult` | Dasha | both |
| Reasoning | `reason(bundle) -> list[Claim]` (+ links) | Dasha | scoring, API |
| Scoring | `score(claims) -> VerdictResult` | Dasha | API, recompute |
| Verification | `verify(claims, bundle) -> VerificationReport` | Dasha | API |
| TAM | `TamEstimate` with ranges and sources (derived) | Arsenii | Dasha (B6, B7) |
| API shapes | `ReportResponse`, `ClaimView`, `EvidenceView`, `DiffResponse` | Arsenii | Dasha (UI) |

## 4. Cross-track dependencies and how each is unblocked

| Task | Needs | Until the real one lands, use |
|---|---|---|
| A4 extraction | B1 `llm.call` | `FakeLLM`; switch at milestone M1 |
| A5 API and UI | claims and report from B | fixture `ReportResponse` JSON |
| A7 recompute | B4 `score()` | the agreed `score()` signature with a stub; real at M3 |
| A8 eval runner | full pipeline | run on fixtures; real at M3 |
| A9 TAM | none | feeds B6 and B7 through `TamEstimate` |
| B2, B3, B6, B9 reasoning | bundles from A | fixture bundles; real bundles at M2 |
| B4 scoring | claims | fixture claims |
| B5 report UI | report JSON from A5 | fixture `ReportResponse` JSON |
| B7 rNPV | TAM from A9 | placeholder distributions in config |
| B8 verification | bundle and claims | fixtures |
| B10 sensitivity tests | A7 add-evidence | write tests against the interface first |

## 5. Phase 0: together, about one day

Do these in parallel where possible, then review each other's work.

- [ ] Both: install, run `scripts/check_compat.py` and `pytest` green on both machines; record resolved versions in `docs/stack.md`.
- [ ] Both: read and accept ADR-001 to ADR-009 (status `Accepted`); set the code-freeze date in `CONTRIBUTING.md`.
- [ ] **Arsenii:** `Connector` protocol, `FakeConnector`, fixture bundle `fixtures/bundles/divarasib.json` (at least 8 evidence items from real documents), API response models and fixture JSON for the UI, split `graph/pipeline.py` into wiring plus `collect_nodes.py`.
- [ ] **Dasha:** `reason`, `score`, `verify` signatures and stubs, `FakeLLM`, fixture bundle `fixtures/bundles/hro761.json` and hand-written fixture claims, `reason_nodes.py` for the reasoning-side DAG nodes.
- [ ] Both: `tests/contract/` with one test per contract (a real bundle validates against the schema; the fixtures load; the fakes satisfy the protocols).

Exit criterion (milestone M0): both can run `uv run bioverdict run --asset divarasib` with `USE_FIXTURES=1` and see the DAG finish, and both UIs can be developed against fixture JSON.

CLI status (2026-10-07): the offline command now runs the fixture pipeline through resolve,
collect, freeze, mechanism/translation reasoning, scoring and JSON report export. It uses the A5
fixture API's SQLite records; live orchestration and the remaining Phase 0 sign-offs are pending.

## 6. Milestones

Frontend status (2026-10-07): approved English dark-console design; Tailwind 4, shared tokens
and typed UI primitives are in `arsenii/A5-design-system`. A5 input/resolver/evidence screens
follow in a separate dependent feature branch. Report and trace remain in Dasha's scope.

| Milestone | Meaning | Who |
|---|---|---|
| M0 | Contracts, fixtures and fakes merged; both start parallel work | both |
| M1 | `llm.call` works for one provider; extraction switches from `FakeLLM` to real | Dasha delivers, Arsenii switches |
| M2 | **Bundle handoff:** a real bundle for divarasib from real connectors passes the bundle contract test; reasoning runs on it | Arsenii delivers, Dasha consumes; short pairing session |
| M3 | **Walking skeleton:** one asset end to end (low quality is fine); both UIs show real data; recompute works at least as "re-run reason and score on bundle v2" | both |
| M4 | Eval run, leakage probe, calibration of thresholds; fix the worst failures | both, joint |
| M5 | Demo freeze, rehearsal, recorded runs | both |

## 7. Working rules

- Branches: `arsenii/<task-id>-<short-name>` and `dasha/<task-id>-<short-name>`.
- `main` always runs. Every PR is reviewed by the other person the same day when possible; the reviewer's job is contracts, tests and the rules in `CONTRIBUTING.md`, not style.
- At most **two tasks in progress** per person.
- Daily sync, 10 minutes: what I finished, what I start, what could block you. Update the status column in this file.
- Contract changes: a PR that edits `docs/data-model.md` or `contracts.py` first; both approve before code changes.
- Pair on M2 and M4. Those are the integration points where bugs concentrate.

## 8. Ownership map

| Area | Owner | Reviewer |
|---|---|---|
| `bioverdict/resolver/`, `bioverdict/connectors/`, `bioverdict/store/` (cache, bundle, versions) | Arsenii | Dasha |
| `bioverdict/graph/collect_nodes.py`, `bioverdict/agents/` (extraction) | Arsenii | Dasha |
| `bioverdict/api/` (all routers), incremental recompute | Arsenii | Dasha |
| `frontend/src/app/`, `frontend/src/features/evidence/` | Arsenii | Dasha |
| `eval/runner`, metrics, cache pre-warm; `docs/runbook.md`, `docs/cost.md` measurements | Arsenii | Dasha |
| `bioverdict/llm/` | Dasha | Arsenii |
| `bioverdict/reasoning/`, `bioverdict/graph/reason_nodes.py`, `bioverdict/playbooks/` | Dasha | Arsenii |
| `bioverdict/scoring/`, `config/scoring.yaml` | Dasha | Arsenii |
| `bioverdict/verify/` | Dasha | Arsenii |
| `frontend/src/features/report/`, `frontend/src/features/trace/` | Dasha | Arsenii |
| `eval/cases.yaml`, sensitivity tests; `docs/eval.md`, `docs/domain-pack-oncology.md`, `docs/demo-script.md` | Dasha | Arsenii |
| **Shared:** `graph/pipeline.py` (wiring only), `docs/data-model.md`, `bioverdict/contracts.py`, `bioverdict/store/models.py`, `pyproject.toml`, lock files | both | each other |

Frontend rule: each person works in their own `features/` folder; the shell, routes and API client belong to Arsenii (A5); Dasha adds her routes in her own folder and registers them in one line.

## 9. Capacity check and scope cuts

Fill in once the deadline is known: working days `D` = TODO, hours per day `H` = TODO. Capacity per person in points is `D x H / 4` (assuming 1 point = 4 hours, which is a guess).

If capacity is lower than the plan, cut **in pairs** so both people lose similar amounts. Remaining points after each cut:

| After | Arsenii | Dasha |
|---|---|---|
| Everything | 47 | 46 |
| Drop P3 | 44 | 43 |
| Drop P2 | 38 | 38 |
| Drop A6 and B9 | 34 | 35 |
| Drop A9 and B6 | 30 | 32 |

Never cut: P0, A7 (or its fallback), B8, B10 (sensitivity tests). They carry the finals requirements: traceability, honesty about unknowns, evidence that changes the verdict.

**A7 fallback.** If claim-level incremental recompute is too costly, show the change by re-running reasoning and scoring on bundle v2 and diffing the two reports. Scoring is deterministic code, so this is fast and the diff screen works the same.

## 10. Re-balancing

- If someone finishes early, they take the next unstarted task from the *other* list in priority order, after agreeing in the daily sync, and move the row between tables with a note.
- If a task is bigger than its estimate by more than one point, split it or move a small task across so totals stay within about two points.
- Re-estimate after M1 and M3.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Contract drifts; late integration breaks | contract tests in `tests/contract/`; M2 pairing session |
| One track blocked on the other | fakes and fixtures; blocked tasks are listed in section 4 |
| Merge conflicts in the frontend and `pipeline.py` | feature folders; wiring-only `pipeline.py`; small PRs |
| Hidden skill mismatch | swap whole tracks early (before M1) |
| Estimates wrong | re-estimate after M1 and M3; use section 10 |
