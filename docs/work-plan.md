# Work plan and role split

Two people, one goal: **near-equal workload, and both of us busy from the first hour.** This document is the source of truth for who does what. Ownership lives here and in `CONTRIBUTING.md`.

| Person | Track | Mission |
|---|---|---|
| **Arsenii** | **A: Evidence and platform** | Everything from the question to a frozen, versioned evidence bundle; the API; the evidence and sources UI; incremental recompute; the eval harness |
| **Dasha** | **B: Reasoning and verdict** | Everything from the frozen bundle to the verdict: LLM layer, reasoning modules, scoring, verification, report UI, eval cases |

## Progress snapshot — 2026-10-07

Checked against merged `main` (100a96e), repository files and open PRs #14, #28, #30–#35,
plus this `arsenii/A4-fixture-collection` branch. Unpublished teammate work is not included.
Update this snapshot after merges or new implementation.

**Legend:** `[x]` complete task implementation merged; `[~]` partial implementation or pending
review; `[ ]` task implementation still to do. A prototype, contract, plan or helper does not
complete the whole task. The **Remaining** column includes integration/calibration follow-up
even for complete components.

| Person | Complete tasks | Partial / pending review | Still to do |
|---|---|---|---|
| Arsenii | 0 of 12 whole tasks | 7: A1, A2, A3, A4, A5, A6, A11 | 5: A7, A8, A9, A10, A12 |
| Dasha | 3 of 13: B1, B2, B4 | 3: B8, B10, B11 | 7: B3, B5, B6, B7, B9, B12, B13 |

These are **whole-task counts, not effort percentages**. Arsenii's cache/storage work is
largely merged, but A3 remains partial while the fixture hash fix and end-to-end live validation
are outstanding. Dasha's merged reasoning/scoring components still need full-pipeline evaluation.

**Ready for review, not merged:**

- [#14](https://github.com/Dashulya-coder/BioVerdict/pull/14): fixture hash correction.
- [#28](https://github.com/Dashulya-coder/BioVerdict/pull/28): Open Targets connector.
- [#30](https://github.com/Dashulya-coder/BioVerdict/pull/30): Resolver part 1; currently based on #28.
- [#32](https://github.com/Dashulya-coder/BioVerdict/pull/32): CT results/pagination/stopped studies and PubMed.
- [#31](https://github.com/Dashulya-coder/BioVerdict/pull/31): fixture API and pipeline.
- [#33](https://github.com/Dashulya-coder/BioVerdict/pull/33): fixture CLI; depends on #31/#14.
- [#34](https://github.com/Dashulya-coder/BioVerdict/pull/34): shared Tailwind design system.
- [#35](https://github.com/Dashulya-coder/BioVerdict/pull/35): functional demo UI; depends on #34 and targets `main`.
  The UI can run without backend PRs. It displays prepared data and does not run underwriting.
- `arsenii/A4-fixture-collection`: bounded collect/extraction → frozen bundle on fixtures;
  independent of the API/CLI/frontend PRs. Live registration and run-lifecycle wiring remain.

**Next for Arsenii:** review/merge the pending A1/A2/A3/A5 work, then wire frontend → fixture
API and live Resolver/collect → frozen bundle. **Next for Dasha:** B3 clinical/competition and
B5 report UI can proceed on fixtures using [the shared styles in #34](https://github.com/Dashulya-coder/BioVerdict/blob/arsenii/A5-design-system/docs/design-system.md); B8 needs an
independent verification implementation. M2/M3 require both tracks.

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
| A1 | Resolver: input formats (indication+mechanism, drug name, company code) to MONDO/EFO, UniProt/Ensembl, ChEMBL/Open Targets IDs; alias disambiguation | P0 | 3 | yes | [~] | Drug/target/disease lookup and confirmed IDs in PR #30 (part 1; depends on #28). | Finish remaining input/alias cases and expose live resolution to API/UI. |
| A2 | Connectors: ClinicalTrials.gov v2 and Open Targets, returning `Evidence` objects | P0 | 4 | yes | [~] | ClinicalTrials.gov connector merged (#19); Open Targets #28 and CT results/pagination/stopped studies #32 ready for review. | Merge pending connectors; wire and verify a real bundle handoff (M2). |
| A3 | HTTP cache, `as_of` filter, source catalog (allowlist), bundle freeze, hash and versions | P0 | 3 | yes | [~] | SQLite, cache/retries, cutoff, canonical IDs, latest-wins, catalog, hash, freeze/load and versions merged. | Merge fixture hash fix #14; validate the complete live collect → freeze flow. |
| A4 | Extraction collect agents: quote + value into `Evidence`, section statuses, bounded tool loops | P0 | 4 | yes | [~] | Bounded injected-tool collection, grounded quote/value extraction, cutoff/latest-wins, honest statuses, budget/deadline handling and collect → freeze DAG implemented in this branch; 29 new tests. | Review/merge; register live connectors and Resolver, then wire the API/CLI lifecycle. Live extraction quality and full graph integration still need validation. |
| A5 | API routes: report, claims, evidence, trace, SSE (stable contract); UI shell, input and resolver screen, evidence/source explorer | P0 | 7 | yes | [~] | Fixture API/report/drill-down/trace/SSE in #31; CLI in #33; shared Tailwind UI in #34; functional input/resolver/evidence/sources in #35. | Review/merge PRs; connect UI to API and add live collection. Resolver and full evidence-list endpoints still needed. |
| A6 | Connectors: PubMed / Europe PMC and openFDA / Drugs@FDA | P1 | 4 |  | [~] | PubMed connector in #32. | Review/merge PubMed; implement openFDA / Drugs@FDA and any additional Europe PMC coverage. |
| A7 | Incremental recompute engine, add-evidence endpoint, diff API and diff screen | P1 | 5 | yes | [ ] | Scoring has a reusable rescore helper; no A7 workflow. | Implement add-evidence, recompute orchestration, report diff API and UI (or the documented full re-run fallback). |
| A8 | Eval runner, grounding and citation metrics, leakage probe, cache pre-warm | P1 | 4 |  | [ ] | Evaluation strategy documented. | Implement runner, grounding/citation metrics, leakage probe and cache pre-warm. |
| A9 | Epidemiology and pricing connectors (SEER, GCO, CMS) and TAM numbers derived by code | P1 | 4 |  | [ ] | TAM contracts/design documented. | Implement epidemiology/pricing retrieval and reproducible TAM calculations. |
| A10 | Connectors: SEC EDGAR and Tavily | P2 | 3 |  | [ ] | Source strategy documented. | Implement SEC EDGAR and Tavily connectors. |
| A11 | Ops: runbook upkeep, cost measurement from the trace table, model bake-off run, demo recordings | P2 | 3 |  | [~] | Runbook and cost/bake-off plans documented; fixture CLI instructions in #33. | Measure real run cost/time/cache/failover; run bake-off; record demos; confirm remaining runbook commands. |
| A12 | Patent/IP connectors (Google Patents links, Orange/Purple Book) and market-sentiment module | P3 | 3 |  | [ ] | Scope documented. | Implement patent/IP sources and market sentiment. |

### Dasha: Track B (Reasoning and verdict)

| ID | Task | Priority | Points | Demo-critical | Status | Implemented / evidence | Remaining |
|---|---|---|---|---|---|---|---|
| B1 | LLM layer: `llm.call`, provider adapters, schema validation and retries, cache, failover, circuit breaker, budget cap, logging | P0 | 5 | yes | [x] | LLM client, Anthropic adapter, validation/retries, cache, failover logic, breaker, budget and logging merged (#18). | Integrate real collection; add further live provider adapters as needed for failover/judge and validate live configuration. |
| B2 | Reasoning modules: mechanism validation and translation chain (supported / weak / missing links) | P0 | 5 | yes | [x] | Mechanism and translation modules, grounding and explicit missing-chain links merged (#26/#29). | Consume real frozen bundles and evaluate quality; remaining clinical modules are B3. |
| B3 | Reasoning modules: clinical development and competition and pipeline | P0 | 4 | yes | [ ] | Generic reasoning framework exists. | Implement clinical development, competition and pipeline modules. |
| B4 | Scoring: gates, claim confidence, probability of success, verdict mapping | P0 | 4 | yes | [x] | Confidence, gates, PoS and deterministic verdict mapping merged (#11/#27); study-fact handling #29. | Calibrate thresholds in M4; wire B7 financial outputs when available. |
| B5 | Report UI: executive verdict, claim drill-down, translation-chain graph | P0 | 4 | yes | [ ] | Shared English dark-console tokens/primitives available in #34. | Implement executive report, claim drill-down and translation graph using the shared design system. |
| B6 | Reasoning modules: disease and unmet need; commercial opportunity (uses TAM numbers from A9) | P1 | 3 |  | [ ] | Domain checklists documented. | Implement disease/unmet-need and commercial modules; consume A9 TAM. |
| B7 | rNPV Monte Carlo, capital and time to milestone, tornado chart | P1 | 3 |  | [ ] | Range/financial output contracts and scoring hooks exist. | Implement Monte Carlo rNPV, capital/time calculation and tornado chart. |
| B8 | Verification: entailment judge (other provider), source authority, temporal validity | P1 | 3 | yes | [~] | Quote/ID grounding in B2; shared cutoff filter. Strict failed-citation claim dropping added by fixture CLI #33. | Implement independent entailment judge, authority/temporal verification and persist verification results. Quote match alone is insufficient. |
| B9 | Skeptic and Chair steps; diligence questions ranked by value of information | P1 | 3 |  | [ ] | Design documented. | Implement Skeptic, Chair and ranked diligence questions. |
| B10 | Eval set: cases and expectations, sensitivity tests (strong, weak, noise), baselines | P1 | 4 | yes | [~] | Reasoning and scoring unit tests cover evidence/confidence/gate behavior. | Create eval cases/expectations, full strong/weak/noise sensitivity runs and baselines; pair with A8/A7. |
| B11 | Domain pack (oncology), docs content: sources, limitations, results, demo script | P2 | 3 |  | [~] | Oncology domain pack, source/limitation docs and demo script exist. | Complete measured eval results and working demo examples after M4; review documented claims against actual output. |
| B12 | Trace and cost panel, progress UI | P2 | 2 |  | [ ] | Trace API/SSE in #31; shared shell in #34. | Implement trace/cost panel and actual run progress in UI. |
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

Phase 0 evidence: contracts, `FakeConnector`, `FakeLLM`, Divarasib's 15-item bundle and
contract tests exist. Compatibility 17/17 and 369 backend tests passed on the CLI branch;
the second machine is unconfirmed. A4 adds collect/freeze graph nodes and grounded extraction
(29 cases, 332 backend tests). HRO761 fixture, reason-side graph nodes and full API
fixture handoff are still outstanding. ADRs remain **Proposed**; code-freeze date remains TODO.
CLI execution is implemented in pending #33, so M0 is not fully merged.

Exit criterion (milestone M0): both can run `uv run bioverdict run --asset divarasib` with `USE_FIXTURES=1` and see the DAG finish, and both UIs can be developed against fixture JSON.

## 6. Milestones

Frontend status (2026-10-07): approved English dark console; Tailwind 4, shared tokens and
typed primitives in #34. Input → resolved assumptions → evidence explorer and original sources
are implemented in #35 with search, filters, cutoffs, verbatim quotes,
original links, keyboard navigation and mobile layout. Prepared Divarasib data only; API wiring
and report/trace remain outstanding. The shared style document is in #34; it is not yet present in this main-based A4 branch.

| Milestone | Meaning | Who | Status / remaining |
|---|---|---|---|
| M0 | Contracts, fixtures and fakes merged; both start parallel work | both | [~] Contracts/fakes/Divarasib exist; merge CLI/API, merge A4 collection; complete reasoning graph/HRO761 and verify both machines. |
| M1 | `llm.call` works for one provider; extraction switches from `FakeLLM` to real | Dasha delivers, Arsenii switches | [~] One-provider LLM layer merged; fixture extraction in A4; live extraction switch remains. |
| M2 | **Bundle handoff:** a real bundle for divarasib from real connectors passes the bundle contract test; reasoning runs on it | Arsenii delivers, Dasha consumes; short pairing session | [ ] Connectors partly pending; live collection → frozen bundle → reasoning not integrated. |
| M3 | **Walking skeleton:** one asset end to end (low quality is fine); both UIs show real data; recompute works at least as "re-run reason and score on bundle v2" | both | [~] Fixture backend path in #31/#33 and demo UI prepared; API-driven UIs/live path/recompute still missing. |
| M4 | Eval run, leakage probe, calibration of thresholds; fix the worst failures | both, joint | [ ] Eval runner/cases, leakage runs and calibration outstanding. |
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
