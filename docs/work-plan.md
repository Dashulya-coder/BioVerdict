# Work plan and role split

Two people, one goal: **near-equal workload, and both of us busy from the first hour.** This document is the source of truth for who does what. Ownership lives here and in `CONTRIBUTING.md`.

| Person | Track | Mission |
|---|---|---|
| **Arsenii** | **A: Evidence and platform** | Everything from the question to a frozen, versioned evidence bundle; the API; the evidence and sources UI; incremental recompute; the eval harness |
| **Dasha** | **B: Reasoning and verdict** | Everything from the frozen bundle to the verdict: LLM layer, reasoning modules, scoring, verification, report UI, eval cases |

## Progress snapshot — 2026-10-09

Checked against merged `main` and the repository files. Unpublished work is not included. Update this snapshot when a task changes state, not on every PR:
the per-task detail lives in the tables below.

**Legend:** `[x]` complete task implementation merged; `[~]` partial implementation merged;
`[ ]` task implementation still to do. A prototype, contract, plan or helper does not
complete the whole task. The **Remaining** column includes integration/calibration follow-up
even for complete components.

| Person | Complete tasks | Partial | Still to do |
|---|---|---|---|
| Arsenii | 1 of 12 whole tasks: A2 | 10: A1, A3, A4, A5, A6, A7, A8, A9, A10, A11 | 1: A12 |
| Dasha | 1 of 13: B4 | 8: B1, B2, B3, B5, B7, B8, B10, B11 | 4: B6, B9, B12, B13 |

These are **whole-task counts, not effort percentages**. The Resolver, the connectors,
collect → freeze, reasoning and scoring are joined into a live run behind `USE_FIXTURES=0`, and
the input, resolver, evidence, compare and report screens run on the API; all of it is merged, and
both Docker images build and serve a fixture run (checked on 2026-10-09). The verdict now carries
probability of success and, when the market can be sized, rNPV with capital and time to
milestone (B7).

The model layer has two adapters (Anthropic, and the organizers' OpenAI-compatible gateway) and
single requests to the gateway were probed. **No whole run with a real model has been measured
yet**: that step is what most of the `[~]` rows of track A still wait for.

**The gateway's limits no longer block that run.** The gateway refuses a request over about
16,000 characters and an answer over about 4,096 tokens (`docs/cost.md`). Every caller now sizes
its prompts by `LLMClient.input_budget`: extraction (#73, #89), the reasoning modules, which read
evidence that does not fit one prompt in up to three batches (#68), and the placing of added
evidence (#70); the gateway preset keeps the output limit under the ceiling and a cut-off answer
is retried shorter (#90). Source text that still does not fit leaves an extraction section
`incomplete`; evidence a reasoning module could not read is listed as omitted in its trace. None
of this has been seen in a whole run yet.

**Next for Arsenii:** the first measured live run together with Dasha (M2/M3): keep its report,
bundle hash, trace, rejected claims, time and cost. Then eval and pre-warm on the real case set
and asset list (A8).
**Next for Dasha:** the rest of the report screen (gates list, ranked diligence questions,
tornado from `/financials`) and the trace panel (B5, B12); sources for the rNPV placeholders
(B7); B8 needs an independent verification implementation. M2/M3 require both tracks.

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

| ID | Task | Priority | Points | Demo-critical | Status | Implemented / evidence | Remaining |
|---|---|---|---|---|---|---|---|
| A1 | Resolver: input formats (indication+mechanism, drug name, company code) to MONDO/EFO, UniProt/Ensembl, ChEMBL/Open Targets IDs; alias disambiguation | P0 | 3 | yes | [~] | Drug, target and disease id lookup with strict name matching (#30), one-call text parsing and `Resolver.resolve()` with `assumptions`; runs first in a live run. | Validate parsing with a real model on the test-list assets; show live resolution in the UI. |
| A2 | Connectors: ClinicalTrials.gov v2 and Open Targets, returning `Evidence` objects | P0 | 4 | yes | [x] | ClinicalTrials.gov (#19), its posted results, stopped studies and pagination (#32) and Open Targets (#28) merged. | Wire the connectors into live collection and verify a real bundle handoff (M2). |
| A3 | HTTP cache, `as_of` filter, source catalog (allowlist), bundle freeze, hash and versions | P0 | 3 | yes | [~] | SQLite, cache/retries/pacing, cutoff, canonical ids, latest-wins, catalog, hash (fixture hash #14), freeze/load and versions merged. Every connector checks a fresh answer before it is cached. | Validate the live collect → freeze flow with a real model. |
| A4 | Extraction collect agents: quote + value into `Evidence`, section statuses, bounded tool loops | P0 | 4 | yes | [~] | Bounded, injected-tool collection with grounded quote/value extraction, cutoff/latest-wins, honest statuses, budget/deadline handling and collect → freeze DAG (#36). Live connectors and the Resolver registered and wired into the API/CLI run lifecycle (`pipeline/live_run.py`). Extraction prompts are sized by the endpoint's limit and a long section is read in batches (#73, #89). | Measure live extraction quality, cost and time with a real model; the per-source caps and the batch limit make large sections `incomplete`. |
| A5 | API routes: report, claims, evidence, trace, SSE (stable contract); UI shell, input and resolver screen, evidence/source explorer | P0 | 7 | yes | [~] | Fixture API/report/drill-down/trace/SSE (#31), CLI (#33) and shared Tailwind UI (#34) and the input/resolver/evidence screens on prepared data (#35) merged. `POST /runs` and the CLI start live runs with `USE_FIXTURES=0`. Resolver and whole-bundle endpoints; the input, resolver and evidence screens run on the API (`pnpm dev:api`), with the snapshot kept as an offline fallback. The header follows the run to its end (reasoning, verdict or failed), a reload or a `?run=` link reopens the run without starting another, and a request that is never answered ends with a message (#76). | Check the screens on a live run with a real model; link to the trace screen (B12) when it lands. |
| A6 | Connectors: PubMed / Europe PMC and openFDA / Drugs@FDA | P1 | 4 |  | [~] | PubMed connector merged (#32); its answers are validated before they are cached. openFDA connector: approvals and current labels of approved analogs, in the competition section of a live run. Europe PMC connector: preprints, in the mechanism section. PubMed Central connector: Results and tables of open-access papers (CC BY, CC0), in the clinical section. | Check the openFDA, preprint and full-text records with a real model, and that the clinical section still fits its 90 seconds with a third source. |
| A7 | Incremental recompute engine, add-evidence endpoint, diff API and diff screen | P1 | 5 | yes | [~] | Add-evidence endpoint that recomputes as a new run on the next bundle version: by default the model only places the new evidence on existing claims and code recomputes (`RECOMPUTE_MODE=classify`); `full` runs every reasoning module again. A code-computed diff API between two finished runs, which also lists a chain link whose confidence moved within one status (#72). Compare screen in the UI (API mode); it waits for the run to finish. | Check a recompute with a real model, in both modes; strong / weak / noise cases with B10. |
| A8 | Eval runner, grounding and citation metrics, leakage probe, cache pre-warm | P1 | 4 |  | [~] | `bioverdict eval` (cases file, repeats, grounding/coverage/stability/cost metrics, post-cutoff citation count, JSON and Markdown report) and `bioverdict warm` (retrieval cache and readiness table for an asset list). Grounding drops are written to `verification_log`. A repeat counts for stability only when all its reasoning calls were answered afresh, not served from the cache (#77). | Run on the real case set and the test-list assets; closed-book leakage probe and bare-LLM baseline; citation support needs the judge (B8). |
| A9 | Epidemiology and pricing connectors (SEER, GCO, CMS) and TAM numbers derived by code | P1 | 4 |  | [~] | Connectors for analog prices (Open Targets approved drugs + CMS Medicare Part D/B spending), cancer incidence (NCI State Cancer Profiles), prevalence (CDC, Orphanet) and US population (World Bank); `market/tam.py` computes patients, price and market size by code; `GET /runs/{id}/market`. Biomarker fraction for a point mutation named in the asset's registry records, counted in the MSK-IMPACT cohort (cBioPortal): lung, pancreas, colorectal. The response says that its ranges are low/middle/high bounds, not percentiles (#78). The market estimate feeds rNPV (B7). | Diseases without an open source (Alzheimer's, MS, MASH, ulcerative colitis, cardiovascular risk); biomarkers that are not point mutations; stage and treated fractions; feed B6. |
| A10 | Connectors: SEC EDGAR and Tavily | P2 | 3 |  | [~] | SEC EDGAR connector: the sponsor's newest 8-K/6-K filings and press-release exhibits, the paragraphs that name the asset, in the flags section of a live run. | Tavily was tried and not built: its results for a drug name were market-research promotions and unrelated news, the relevant releases came back without text, and without dates (2026-10-09). Sponsors whose registry name is not their SEC name; 10-K/20-F pipeline sections are not read. |
| A11 | Ops: runbook upkeep, cost measurement from the trace table, model bake-off run, demo recordings | P2 | 3 |  | [~] | Runbook covers fixture and live runs, eval, warm and `bioverdict doctor` (setup, caches, fixtures and source reachability, no model call). Backend and frontend Docker images use the project runtimes, frozen lockfiles, non-root users and health checks; the runbook documents container startup and persistent data. `compose.yaml` starts both with one command, and CI builds the images and runs a fixture run through them. | Measure real run cost/time/cache/failover; run bake-off; record demos. |
| A12 | Patent/IP connectors (Google Patents links, Orange/Purple Book) and market-sentiment module | P3 | 3 |  | [ ] | Scope documented. | Implement patent/IP sources and market sentiment. |

### Dasha: Track B (Reasoning and verdict)

| ID | Task | Priority | Points | Demo-critical | Status | Implemented / evidence | Remaining |
|---|---|---|---|---|---|---|---|
| B1 | LLM layer: `llm.call`, provider adapters, schema validation and retries, cache, failover, circuit breaker, budget cap, logging | P0 | 5 | yes | [~] | LLM client, validation/retries, cache, failover logic, breaker, budget, deadline and logging merged (#18). Two adapters: Anthropic, and an OpenAI-compatible one for the organizers' gateway, with the provider chosen by `LLM_PROVIDER` or by the key that is set (#64, #65). Requests over the gateway's size limit are refused before they are sent (#66); the gateway's output-token ceiling is respected and a cut-off answer is retried shorter (#90). The budget cap counts the worst case of the parallel calls still under way, so a run passes it by at most one call (#75). | Single requests to the gateway were probed; no whole run. The gateway has one vendor's models, so a cross-provider judge needs another adapter. |
| B2 | Reasoning modules: mechanism validation and translation chain (supported / weak / missing links) | P0 | 5 | yes | [~] | Mechanism and translation modules, grounding and explicit missing-chain links merged (#26/#29/#37). Evidence that does not fit one prompt is read in batches sized by the endpoint's limit, for the modules (#68) and for placing added evidence (#70). | No real model answer has been seen: validate prompt and output quality on a live run; remaining modules are B3. |
| B3 | Reasoning modules: clinical development and competition and pipeline | P0 | 4 | yes | [~] | Clinical and competition modules (with K1/K2/K4/S4 evidence guards, a stop-reason classifier and `study_fact` rules) run on the divarasib fixture. | Run on real bundles and live model output; add a pipeline section (programs in development) once connectors feed it; calibrate the guards on the eval set. |
| B4 | Scoring: gates, claim confidence, probability of success, verdict mapping | P0 | 4 | yes | [x] | Confidence, gates, PoS and deterministic verdict mapping merged (#11/#27); study-fact handling #29. Supporting evidence that adds no weight does not count as a second independent source for a hard gate (#74). PoS and rNPV from B7 are in the verdict (#85). | Calibrate thresholds in M4. |
| B5 | Report UI: executive verdict, claim drill-down, translation-chain graph | P0 | 4 | yes | [~] | Report screen (`#report`, API mode): executive verdict, modeled ranges, risks, assumptions, translation chain, claim drill-down to verbatim quotes (#86), and what is unknown grouped by the diligence that could answer it (#91). | Gates list, ranked diligence questions (B9), tornado from `/financials`; check on a live run. |
| B6 | Reasoning modules: disease and unmet need; commercial opportunity (uses TAM numbers from A9) | P1 | 3 |  | [ ] | Domain checklists documented. | Implement disease/unmet-need and commercial modules; consume A9 TAM. |
| B7 | rNPV Monte Carlo, capital and time to milestone, tornado chart | P1 | 3 |  | [~] | Engine (`scoring/rnpv.py`, #79), stage/market wiring into the verdict and `GET /runs/{id}/financials` with the tornado (#85). The stage is the asset's stage in the run's indication when the bundle gives one. Non-market inputs are labeled placeholders; until they are calibrated K5 is a near miss, not a kill, and a ceiling-sized market gives no rNPV (#88). | Calibrate the placeholder inputs (needs sources), then set `rnpv_calibrated`; tornado chart in the UI (B5). |
| B8 | Verification: entailment judge (other provider), source authority, temporal validity | P1 | 3 | yes | [~] | Quote/ID grounding in B2; shared cutoff filter. Strict failed-citation claim dropping added by fixture CLI #33. | Implement independent entailment judge, authority/temporal verification and persist verification results. Quote match alone is insufficient. |
| B9 | Skeptic and Chair steps; diligence questions ranked by value of information | P1 | 3 |  | [ ] | Design documented. | Implement Skeptic, Chair and ranked diligence questions. |
| B10 | Eval set: cases and expectations, sensitivity tests (strong, weak, noise), baselines | P1 | 4 | yes | [~] | Reasoning and scoring unit tests cover evidence/confidence/gate behavior. | Create eval cases/expectations, full strong/weak/noise sensitivity runs and baselines; pair with A8/A7. |
| B11 | Domain pack (oncology), docs content: sources, limitations, results, demo script | P2 | 3 |  | [~] | Oncology domain pack, source/limitation docs and demo script exist. | Complete measured eval results and working demo examples after M4; review documented claims against actual output. |
| B12 | Trace and cost panel, progress UI | P2 | 2 |  | [~] | Trace API/SSE in #31; shared shell in #34; `bioverdict cost` (#95). Trace screen (`#trace`, API mode): cost, tokens and calls of the run, cost by step, every model call with its model, time, cache hit, failover and error, and the steps in order; it follows a running run. | Check on a live run; link a step to its claims; progress bar from the SSE stream. |
| B13 | Reasoning modules: IP/regulatory and red/green flags | P3 | 3 |  | [ ] | IP/regulatory design documented. | Implement reasoning modules and red/green flags. |

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

- [~] Both: install, run `scripts/check_compat.py` and `pytest` green on both machines; record resolved versions in `docs/stack.md`.
- [ ] Both: read and accept ADR-001 to ADR-009 (status `Accepted`); set the code-freeze date in `CONTRIBUTING.md`.
- [~] **Arsenii:** `Connector` protocol, `FakeConnector`, fixture bundle `fixtures/bundles/divarasib.json` (at least 8 evidence items from real documents), API response models and fixture JSON for the UI, split `graph/pipeline.py` into wiring plus `collect_nodes.py`.
- [~] **Dasha:** `reason`, `score`, `verify` signatures and stubs, `FakeLLM`, fixture bundle `fixtures/bundles/hro761.json` and hand-written fixture claims, `reason_nodes.py` for the reasoning-side DAG nodes.
- [~] Both: `tests/contract/` with one test per contract (a real bundle validates against the schema; the fixtures load; the fakes satisfy the protocols).

Phase 0 evidence: contracts, `FakeConnector`, `FakeLLM`, Divarasib's 15-item bundle, the
contract tests, the collect → freeze graph, the fixture API and the CLI are merged. Still open:
the HRO761 fixture, reason-side graph nodes (`reason_nodes.py`), a confirmed setup on the second
machine. ADRs remain **Proposed**; the code-freeze date remains TODO.

Exit criterion (milestone M0): both can run `uv run bioverdict run --asset divarasib` with `USE_FIXTURES=1` and see the DAG finish, and both UIs can be developed against fixture JSON.

CLI status: `bioverdict run` runs the fixture pipeline offline and, with `USE_FIXTURES=0`, the
live one; `eval`, `warm` and `doctor` are described in the [runbook](runbook.md).

## 6. Milestones

Frontend status: the English dark console with shared tokens and typed primitives. Input →
resolved assumptions → evidence explorer and sources, and comparing runs, work on the API
(`pnpm dev:api`) and on the prepared Divarasib snapshot. The report screen (B5) works on the API:
executive verdict, modeled ranges, translation chain, claim drill-down and open questions; its
gates list, ranked questions and tornado are not built. The trace screen (B12) shows the cost and the
calls of a run.

| Milestone | Meaning | Who | Status / remaining |
|---|---|---|---|
| M0 | Contracts, fixtures and fakes merged; both start parallel work | both | [~] Contracts, fakes, the Divarasib fixture, collection, API and CLI are merged. Open: HRO761 fixture, reason-side graph nodes, the second machine. |
| M1 | `llm.call` works for one provider; extraction switches from `FakeLLM` to real | Dasha delivers, Arsenii switches | [~] The LLM layer has two adapters and extraction is wired to it in the live run; single requests to the gateway were probed, and every prompt is sized to the gateway's request and output limits. Open: a whole run. |
| M2 | **Bundle handoff:** a real bundle for divarasib from real connectors passes the bundle contract test; reasoning runs on it | Arsenii delivers, Dasha consumes; short pairing session | [~] Live collection → frozen bundle → reasoning is integrated and merged. Open: a real bundle from a run with a real model, handed over in a pairing session. |
| M3 | **Walking skeleton:** one asset end to end (low quality is fine); both UIs show real data; recompute works at least as "re-run reason and score on bundle v2" | both | [~] One asset runs end to end on fixtures and, with a stand-in model, on real sources; the evidence UI runs on the API; the report screen shows the verdict, the chain and the claims with their quotes; recompute re-runs reasoning on bundle v2 and the diff screen shows it. Open: a real-model run; the rest of the report UI (B5) and the trace panel (B12). |
| M4 | Eval run, leakage probe, calibration of thresholds; fix the worst failures | both, joint | [ ] The eval runner and its metrics are merged; the case set has one smoke case. Open: real cases (B10), closed-book leakage probe, baseline, calibration. |
| M5 | Demo freeze, rehearsal, recorded runs | both | [ ] Freeze date, rehearsal and recorded runs outstanding. |

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
| `frontend/src/app/`, `frontend/src/features/input/`, `frontend/src/features/evidence/` | Arsenii | Dasha |
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
