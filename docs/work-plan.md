# Work plan and role split

Two people, one goal: **near-equal workload, and both of us busy from the first hour.** This document is the source of truth for who does what. Ownership lives here and in `CONTRIBUTING.md`.

| Person | Track | Mission |
|---|---|---|
| **Arsenii** | **A: Evidence and platform** | Everything from the question to a frozen, versioned evidence bundle; the API; the evidence and sources UI; incremental recompute; the eval harness |
| **Dasha** | **B: Reasoning and verdict** | Everything from the frozen bundle to the verdict: LLM layer, reasoning modules, scoring, verification, report UI, eval cases |

## Progress snapshot — 2026-10-10

Checked against merged `main` (through #108) and the repository files. Unpublished work is not
included. Update this snapshot when a task changes state, not on every PR: the per-task detail
lives in the tables below.

**Legend:** `[x]` complete task implementation merged; `[~]` partial implementation merged;
`[ ]` task implementation still to do. A prototype, contract, plan or helper does not
complete the whole task. The **Remaining** column includes integration/calibration follow-up
even for complete components.

| Person | Complete tasks | Partial | Still to do |
|---|---|---|---|
| Arsenii | 1 of 12 whole tasks: A2 | 10: A1, A3, A4, A5, A6, A7, A8, A9, A10, A11 | 1: A12 |
| Dasha | 1 of 13: B4 | 11: B1, B2, B3, B5, B6, B7, B8, B9, B10, B11, B12 | 1: B13 |

These are **whole-task counts, not effort percentages**. Every stage of the pipeline exists and
is joined: resolve, collect, freeze, six reasoning modules, Skeptic, entailment judge, scoring
with PoS and rNPV, Chair. The input, resolver, evidence, report, compare and trace screens run on
the API, and both Docker images build and serve a fixture run.

**Whole runs with a real model have been made** (2026-10-10, #105): three for BTK inhibitor x
multiple sclerosis on the organizers' gateway. The last took 5 min 7 s and $0.99: verdict
Conditional, 72 citations judged and 13 removed, 8 ranked diligence questions. That is one
question on one day: no other asset and no repeat for stability. A recompute has been run
with a real model only five times, in `classify` mode, in the sensitivity benchmark; `full`
mode has not been run. What the first run broke and #105 fixed is listed in that pull request.
**Nothing merged after the third run has been run with a real model**: the end of #105 and all
of #107.

**After those runs (#107)**, from a second audit of the same day: a recompute rejects a new
claim whose citation fails and shows an analyst's document to every module in full mode;
registry results keep the arm of every number, are dated by the record's last update, and say
when a limit cut them; a run without a drug is labelled a class landscape and offers the drugs
of experimental arms to choose from. `docs/handoff.md` (#108) holds the note that hands the
paid runs and the open questions to Dasha; `AGENTS.md` tells a coding agent to read it first.

**The finals rubric** (`docs/demo-script.md`) scores six modules on conflicting evidence,
evidence flow and quality for that pair. For it the report gives an answer per module, computed
by code (`docs/scoring.md`, "Module answers"), the diff gives each module before and after with
the evidence that moved it, and `bioverdict sensitivity` checks strong, weak and noise documents
against `eval/sensitivity.yaml`.

**Done on 2026-10-10 (Dasha):** a live run of the pair on merged `main`, a base run with
`--as-of 2024-06-30` and the sensitivity benchmark on it (3 of 5 passed; `docs/eval.md`,
section 9). The five recomputes of that benchmark, in `classify` mode, are the only recomputes
run with a real model: `full` mode has not been run. `RUN_TIMEOUT_S` is 900 in `.env` on
Dasha's machine; check the `.env` of the demo machine (a copy of the old `.env.example` says
420) and pre-warm the model cache.

**Still open from before:** no patient count for multiple sclerosis in the connectors, so no
market size and no rNPV for the demo pair (A9); the same trial result is restated by the
mechanism, translation and clinical modules and counts in each; the two thresholds of a
module's answer (0.2 and 0.25) are uncalibrated.

### Final plan (set 2026-10-10)

Made after a second live run of the pair (`R-20261010-125211-cf5016`, Conditional, $0.87) and a
check of its report against the finals rubric (`demo-script.md`). Each item is tied to a
module and a criterion (**A** conflicting evidence, **B** evidence flow, **C** quality for the
pair), and its result has to be visible on screen. What that run showed: no evidence and no
claim on liver injury, the EU authorisation of tolebrutinib (Cenrifki, 2026-06-19), FENtrepid
or the fenebrutinib filing; no approved MS drug in any claim (the competition section
restates trial results, and the commercial section holds FDA labels of analogs by target:
lymphoma, CLL, alopecia, thrombocytopenia);
only 39 of 156 evidence records cited, and 6 of the 11 registry trials cited by no claim,
PERSEUS among them; the "top risks" are gate texts. The table of the reference set is in
`docs/eval.md`, section 9.

**Stage 0: now, no paid calls (Dasha).** Three pull requests: (a) documents, (b) her track,
(c) the areas of A7 and A8, which Arsenii reviews.

| # | What | Criterion / module | Done when | PR |
|---|---|---|---|---|
| 0.1 | Merge #112 (why the judge removed a quote) | B, all | in `main` | |
| 0.2 | Fix "no approval yet" in `eval.md` and `cases.yaml`: EU authorisation 2026-06-19 (EMA); FDA complete response letter 2025-12-24 (Sanofi) | C | no fact without a primary source | a |
| 0.3 | Top risks from unfavourable and key claims, with claim ids, not gate texts. `VerdictResult.top_risks` is `list[str]` in the shared `store/models.py`: an additive field first goes through a PR in `data-model.md` that both approve (`CONTRIBUTING.md`) | B, C / investment | each risk opens its claim and then its quote | b |
| 0.4 | Mark links of context claims "not judged" (48 in the run) instead of "Source fact"; additive API field, Arsenii reviews | B, all | the screen does not show the unchecked as checked | b |
| 0.5 | A `classify` recompute can attach a new claim to a chain link and replace an `unknown` (decision 7 of `handoff.md`) | A / translation | test: a document on exposure moves Human exposure from Missing to Weak. It will not by itself move the verdict: S2 and key claims below 0.7 also hold it at Conditional | c |
| 0.6 | Sensitivity runner: one control recompute at the shared cutoff without a document; each case is compared with it, not with the base | A, all | the noise case passes under the strict rule, with no exception for drift | c |
| 0.7 | Reference-set coverage table: source x in the bundle x cited by a claim, labelled "development set, written by us" | C | table in `eval.md`, section 9 | a |

**Stage 1: collection for multiple sclerosis.** Done by Dasha on 2026-10-10 without waiting for
Arsenii (his consent was waived): `openfda_indication` (approved drugs of the indication with
their labels), `ema_medicines` (the EU register: Cenrifki and the approved competitors) and
`pubmed_safety` (class safety, reviews as one source), see `collection.md`. Found on the way: the
competition module read only the families `registry` and `target_database`, so no FDA label
reached it; it reads `approved_for_indication` now. **Not done:** fewer oncology analogs (still
8 per target); the FDA complete response letter (Sanofi, 2025-12-24) has no source; the EPAR
text; why 6 of 11 registry trials stay uncited; a live run to see what the modules make of it.
If collection falls short, the reference documents enter through add-evidence on stage, which is
also a demonstration of A.

**Stage 2: before the mentor.** Stage 0 plus one slide: what the system knows about the pair,
what it lacks (liver, EU authorisation, FENtrepid, PERSEUS without claims) and the plan, with
the "before" numbers of 0.7.

**Stage 3: after collection, paid runs (Dasha; Arsenii for 3.2).** Before any budget, measure the time and cost of one recompute: the
base run and the five recomputes of 2026-10-10 are not in `backend/data/bioverdict.sqlite`
and `eval/results/` does not exist on the machine checked.

| # | What | For |
|---|---|---|
| 3.1 | A live run of the pair on the new collection | C, all modules; coverage "after" |
| 3.2 | Joint decision on balance calibration (thresholds 0.2 and 0.25; count by trial or by claim), from 3.1 | stability of answers, A and C |
| 3.3 | A base for sensitivity with a cutoff before the reference documents, and one control recompute | A |
| 3.4 | One case per module (matrix below) | A, all six |
| 3.5 | Stability: two fresh reasoning runs on one bundle (same bundle hash) | C; "same input, same verdict" |
| 3.6 | One backtest with a clean date (`evobrutinib-2023-11`), noting that quote selection may draw on the model's memory | C, benchmark |

| Module | A: the case | Note |
|---|---|---|
| Unmet need | PERSEUS (failure in PPMS) | |
| Mechanism | the weak preprint, expecting almost no move | exists |
| Translation | a document on human exposure: Missing to Weak | after 0.5 |
| Clinical | tolebrutinib and evobrutinib cases | exist, pass |
| Competitive | FENtrepid, or FDA acceptance of the fenebrutinib filing | after stage 1 |
| Investment | a strong negative (stopped program, clinical hold) that reaches a hard gate; liver safety or the EU authorisation moves gates and PoS but not the label | K2 and K4 fire on keywords: negative controls first |
| Controls | noise (KRAS), another population | |

**Stage 4: the benchmark, human time only.** (4.1) Label 30 judge decisions (Dasha exports the
table of removals). (4.2) One table: the sensitivity cases per module (strong, weak, noise and
a control), reference-set coverage before and after, judge agreement, stability and one
backtest; the method in two sentences; every dataset item named (PMID, NCT, URL).

**Stage 5: the demo (UI 10 and delivery).** Record runs and keep their bundle hashes as the
fallback (a run of six minutes does not fit on stage); 40 seconds per module: B (click to the
source), A (before and after, with the cause), C (one sentence); check Report and Compare on
the recorded run.

**If time is short, the minimum is:** 0.1 to 0.4, 0.7, the note to Arsenii, the live run after
collection (3.1), and A-cases for four of the six modules (clinical and mechanism already
exist; take two of the other four).

**Open, to decide with Arsenii:** balance calibration (3.2); whether to add EMA to the source
catalog; approval of `Claim.implication`, which entered the shared contract without the
two-step approval.

The second audit is in [`finals-audit.md`](finals-audit.md): 17 findings with their status, a
reference set of seven named BTK x MS sources, and a benchmark method. Its open findings
(verification that keeps unanswered links, kill-criteria guards, counting one trial several
times, MS competitors missing from the analogs) are not in the list above; they are in
[`handoff.md`](handoff.md) with the nine decisions the two of us have not made together.

**Next for Dasha:** stage 0 of the final plan above, then what the runs show in her modules
(`handoff.md`, section 2).
**Next for Arsenii:** stage 1 (the note to him in `handoff.md`); item 4 if an open source for
prevalence is found; keeping the recorded runs, their bundle hashes and costs for the demo (A11).

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
| A1 | Resolver: input formats (indication+mechanism, drug name, company code) to MONDO/EFO, UniProt/Ensembl, ChEMBL/Open Targets IDs; alias disambiguation | P0 | 3 | yes | [~] | Drug, target and disease id lookup with strict name matching (#30), one-call text parsing and `Resolver.resolve()` with `assumptions`; runs first in a live run. A term that holds a disease's subtypes is taken for the disease: Open Targets files multiple sclerosis under "multiple sclerosis symptom measurement" (#105). Parsing "BTK inhibitor for multiple sclerosis" was seen with a real model. | Validate parsing on the test-list assets and the other input formats with a real model. |
| A2 | Connectors: ClinicalTrials.gov v2 and Open Targets, returning `Evidence` objects | P0 | 4 | yes | [x] | ClinicalTrials.gov (#19), its posted results, stopped studies and pagination (#32) and Open Targets (#28) merged. They feed live collection (real bundles of 156 to 161 items on 2026-10-10). Registry results keep the arm id of each measurement and analysis, are dated by the record's last update, and report a search or result list cut by a limit; the design record keeps arms and interventions (#107). | The #107 changes have not been seen on a live run; a time-travel run now sees fewer registry results. |
| A3 | HTTP cache, `as_of` filter, source catalog (allowlist), bundle freeze, hash and versions | P0 | 3 | yes | [~] | SQLite, cache/retries/pacing, cutoff, canonical ids, latest-wins, catalog, hash (fixture hash #14), freeze/load and versions merged. Every connector checks a fresh answer before it is cached. | Validate the live collect → freeze flow with a real model. |
| A4 | Extraction collect agents: quote + value into `Evidence`, section statuses, bounded tool loops | P0 | 4 | yes | [~] | Bounded, injected-tool collection with grounded quote/value extraction, cutoff/latest-wins, honest statuses, budget/deadline handling and collect → freeze DAG (#36). Live connectors and the Resolver registered and wired into the API/CLI run lifecycle (`pipeline/live_run.py`). Extraction prompts are sized by the endpoint's limit and a long section is read in batches (#73, #89). The unmet-need section reads the newest PubMed practice guidelines for the indication (`pubmed_guidelines`). | Measure live extraction quality, cost and time with a real model; the per-source caps and the batch limit make large sections `incomplete`. |
| A5 | API routes: report, claims, evidence, trace, SSE (stable contract); UI shell, input and resolver screen, evidence/source explorer | P0 | 7 | yes | [~] | Fixture API/report/drill-down/trace/SSE (#31), CLI (#33) and shared Tailwind UI (#34) and the input/resolver/evidence screens on prepared data (#35) merged. `POST /runs` and the CLI start live runs with `USE_FIXTURES=0`. Resolver and whole-bundle endpoints; the input, resolver and evidence screens run on the API (`pnpm dev:api`), with the snapshot kept as an offline fallback. The header follows the run to its end (reasoning, verdict or failed), a reload or a `?run=` link reopens the run without starting another, and a request that is never answered ends with a message (#76). A run without a drug is labelled a class landscape and the resolved-input screen lists the drugs of experimental arms, each with its studies; choosing one pre-fills a new analysis. A reopened run keeps its indication and mechanism (#107). | Look at the screens on a live run with a real model. Choosing an asset starts a second whole run. |
| A6 | Connectors: PubMed / Europe PMC and openFDA / Drugs@FDA | P1 | 4 |  | [~] | PubMed connector merged (#32); its answers are validated before they are cached. openFDA connector: approvals and current labels of approved analogs, in the competition section of a live run. Europe PMC connector: preprints, in the mechanism section. PubMed Central connector: Results and tables of open-access papers (CC BY, CC0), in the clinical section. | Check the openFDA, preprint and full-text records with a real model, and that the clinical section still fits its 90 seconds with a third source. |
| A7 | Incremental recompute engine, add-evidence endpoint, diff API and diff screen | P1 | 5 | yes | [~] | Add-evidence endpoint that recomputes as a new run on the next bundle version: by default the model only places the new evidence on existing claims and code recomputes (`RECOMPUTE_MODE=classify`); `full` runs every reasoning module again. A code-computed diff API between two finished runs, which also lists a chain link whose confidence moved within one status (#72). Compare screen in the UI (API mode); it waits for the run to finish. The diff lists each of the six modules before and after, with the new evidence, quote and claim that moved it, and Compare shows it (#105). In classify mode a new claim with a failed citation, or with none, is rejected whole and logged; in full mode an analyst's document is shown to every module (before, no module read it) (#107). In classify mode a new fact that shows a translation-chain link is grounded as a translation claim with its `chain_link` and retires the `unknown` claim of that link, so a link can move from missing to weak and gate S1 can clear (fake model). | Check that path with a real model, and a recompute in `full` mode (the sensitivity cases of 2026-10-10 recomputed with a real model in the default mode). Evidence the model links to the `unknown` claim itself is not placed on the chain. |
| A8 | Eval runner, grounding and citation metrics, leakage probe, cache pre-warm | P1 | 4 |  | [~] | `bioverdict eval` (cases file, repeats, grounding/coverage/stability/cost metrics, post-cutoff citation count, JSON and Markdown report) and `bioverdict warm` (retrieval cache and readiness table for an asset list). Grounding drops are written to `verification_log`. A repeat counts for stability only when all its reasoning calls were answered afresh, not served from the cache (#77). `bioverdict sensitivity`: adds documents to a finished run and checks from the code-computed diff which modules moved (#105); each case is compared with one control recompute at the same cutoff with no document, so a later cutoff is not read as an effect, and the noise rule has no drift exception. | Run `eval` on the real case set and the test-list assets: not run with a real model. `sensitivity` ran once on 2026-10-10 (3 of 5), before the control: run it again. Closed-book leakage probe and bare-LLM baseline. |
| A9 | Epidemiology and pricing connectors (SEER, GCO, CMS) and TAM numbers derived by code | P1 | 4 |  | [~] | Connectors for analog prices (Open Targets approved drugs + CMS Medicare Part D/B spending), cancer incidence (NCI State Cancer Profiles), prevalence (CDC, Orphanet) and US population (World Bank); `market/tam.py` computes patients, price and market size by code; `GET /runs/{id}/market`. Biomarker fraction for a point mutation named in the asset's registry records, counted in the MSK-IMPACT cohort (cBioPortal): lung, pancreas, colorectal. The response says that its ranges are low/middle/high bounds, not percentiles (#78). The market estimate feeds rNPV (B7). | Diseases without an open source (Alzheimer's, MS, MASH, ulcerative colitis, cardiovascular risk): the demo pair is one of them, so it has no market size and no rNPV; biomarkers that are not point mutations; stage and treated fractions; feed B6. |
| A10 | Connectors: SEC EDGAR and Tavily | P2 | 3 |  | [~] | SEC EDGAR connector: the sponsor's newest 8-K/6-K filings and press-release exhibits, the paragraphs that name the asset, in the flags section of a live run. | Tavily was tried and not built: its results for a drug name were market-research promotions and unrelated news, the relevant releases came back without text, and without dates (2026-10-09). Sponsors whose registry name is not their SEC name; 10-K/20-F pipeline sections are not read. |
| A11 | Ops: runbook upkeep, cost measurement from the trace table, model bake-off run, demo recordings | P2 | 3 |  | [~] | Runbook covers fixture and live runs, eval, warm and `bioverdict doctor` (setup, caches, fixtures and source reachability, no model call). Backend and frontend Docker images use the project runtimes, frozen lockfiles, non-root users and health checks; the runbook documents container startup and persistent data. `compose.yaml` starts both with one command, and CI builds the images and runs a fixture run through them. First measured live runs: $0.90 to $1.20 and 3 min 45 s to 7 min 21 s for BTK inhibitor x multiple sclerosis on the gateway, the judge about 60% of the cost (#105). | Measure other assets, cache hits and failover; run bake-off; record demos; `docs/cost.md` does not hold these numbers yet. |
| A12 | Patent/IP connectors (Google Patents links, Orange/Purple Book) and market-sentiment module | P3 | 3 |  | [ ] | Scope documented. | Implement patent/IP sources and market sentiment. |

### Dasha: Track B (Reasoning and verdict)

| ID | Task | Priority | Points | Demo-critical | Status | Implemented / evidence | Remaining |
|---|---|---|---|---|---|---|---|
| B1 | LLM layer: `llm.call`, provider adapters, schema validation and retries, cache, failover, circuit breaker, budget cap, logging | P0 | 5 | yes | [~] | LLM client, validation/retries, cache, failover logic, breaker, budget, deadline and logging merged (#18). Two adapters: Anthropic, and an OpenAI-compatible one for the organizers' gateway, with the provider chosen by `LLM_PROVIDER` or by the key that is set (#64, #65). Requests over the gateway's size limit are refused before they are sent (#66); the gateway's output-token ceiling is respected and a cut-off answer is retried shorter (#90). The budget cap counts the worst case of the parallel calls still under way, so a run passes it by at most one call (#75). Requests above the gateway's concurrency limit wait their turn (`LLM_MAX_CONCURRENCY`, default 4): a fifth got 429 and a slow failover (#105). | Three whole runs on the gateway, one question. The limit of 4 is from one observation. The gateway has one vendor's models, so a cross-provider judge needs another adapter. |
| B2 | Reasoning modules: mechanism validation and translation chain (supported / weak / missing links) | P0 | 5 | yes | [~] | Mechanism and translation modules, grounding and explicit missing-chain links merged (#26/#29/#37). Evidence that does not fit one prompt is read in batches sized by the endpoint's limit, for the modules (#68) and for placing added evidence (#70). Every prompt states the resolved question; one fact per claim; each claim carries an `implication` for the module answers; mechanism and translation read preprints (#105). | Seen on one live question. The modules restate one another's trial results; check on other assets. |
| B3 | Reasoning modules: clinical development and competition and pipeline | P0 | 4 | yes | [~] | Clinical and competition modules (with K1/K2/K4/S4 evidence guards, a stop-reason classifier and `study_fact` rules) run on the divarasib fixture. | Run on real bundles and live model output; add a pipeline section (programs in development) once connectors feed it; calibrate the guards on the eval set. |
| B4 | Scoring: gates, claim confidence, probability of success, verdict mapping | P0 | 4 | yes | [x] | Confidence, gates, PoS and deterministic verdict mapping merged (#11/#27); study-fact handling #29. Supporting evidence that adds no weight does not count as a second independent source for a hard gate (#74). PoS and rNPV from B7 are in the verdict (#85). | Calibrate thresholds in M4. Top risks name their claims (`top_risk_claims`, option B in `docs/data-model.md`): kill criteria, then the claims that pull hardest against investing, one per independence group; the Report links each risk to its claim and quotation. Not yet seen on a live run. |
| B5 | Report UI: executive verdict, claim drill-down, translation-chain graph | P0 | 4 | yes | [~] | Report screen (`#report`, API mode): executive verdict, modeled ranges, risks, assumptions, translation chain, claim drill-down to verbatim quotes (#86), and what is unknown grouped by the diligence that could answer it (#91). Gates list (#97), rNPV tornado from `/financials` (#98) and a ranked-questions list, filled by the Chair step (B9). "Six modules, six answers": each module's answer, the weight on each side, and its claims down to quotes and source links (#105). | Seen on a live run (2026-10-10): verdict, six answers, gates, chain, drill-down. The "top risks" are still gate texts. |
| B6 | Reasoning modules: disease and unmet need; commercial opportunity (uses TAM numbers from A9) | P1 | 3 |  | [~] | `unmet_need` and `commercial` modules on the common reasoner (steps `reasoning.unmet_need`, `reasoning.commercial`), canned answers in the Divarasib fixture. Neither asserts a gate; the market numbers stay with code and never reach a model, so `commercial` writes differentiation claims and honest unknowns (pricing, coverage, launch plan). | There is no collection plan for the unmet-need section (guidelines, standard of care), so on a live run its claims rest on what the other sections fetched; the TAM figures (A9) are shown by `/runs/{id}/market`, not in a claim; check on a live model. |
| B7 | rNPV Monte Carlo, capital and time to milestone, tornado chart | P1 | 3 |  | [~] | Engine (`scoring/rnpv.py`, #79), stage/market wiring into the verdict and `GET /runs/{id}/financials` with the tornado (#85). The stage is the asset's stage in the run's indication when the bundle gives one. Non-market inputs are labeled placeholders; until they are calibrated K5 is a near miss, not a kill, and a ceiling-sized market gives no rNPV (#88). | Calibrate the placeholder inputs (needs sources), then set `rnpv_calibrated`; tornado chart in the UI (B5). |
| B8 | Verification: entailment judge (other provider), source authority, temporal validity | P1 | 3 | yes | [~] | Quote/ID grounding in B2; shared cutoff filter. Entailment judge (step `judge`) reads every claim with every quote cited for it; a link it does not confirm is removed, a claim left bare becomes a hypothesis, confidences follow by formula; it also reads the Skeptic's objections and the links a recompute places. Judge on the other vendor when both keys are set, otherwise a stronger model of the same vendor. Authority and temporal rules log why a claim is weak. Results are in `verification_log`; the eval runner reports the share of judged links confirmed. The judge reads a quote with its passage and record id (alone it removed 75 of 93 citations on the first live run, 13 of 72 after); a failed request leaves its links unjudged instead of cancelling the check; links of context claims are not judged (#105). A registry result record is shown to the judge as lines (value beside its group name): before, the numbers lay outside its 450-character window and it removed 10 of the 13 removals of a sample for that reason alone (`docs/eval.md`, section 9). The claim drill-down shows the checks a claim failed (the judge's reason for a removed quote, a weak source, a downgrade) from `verification_log`, in `ClaimView.checks`; each link shows whether the judge read it (`LinkView.judged`: judged, not judged, no answer). | Re-run the judge on the 30 labelled rows (and read the other 26) after the fix; decide the rule on a background fact that keeps a main point (rows 14, 27). Check on both vendors. |
| B9 | Skeptic and Chair steps; diligence questions ranked by value of information | P1 | 3 |  | [~] | Skeptic (grounded objections become `contradicts` links, confidence recomputed by the formula) and Chair (questions about claims) as model steps after reasoning; questions ranked by code from the verdict recomputed for each answer (`scoring/voi.py`); both steps are advisory and a failed call is logged as skipped. Fixture run, live run and the recompute path produce `diligence_questions`. | The Chair's targeted second collection round (bundle v2); measure on more than one live question (on the one run the Skeptic grounded 0 to 2 objections and the Chair returned 8 questions, once its claim list was sized to the request limit, #105); calibrate the VoI placeholders. |
| B10 | Eval set: cases and expectations, sensitivity tests (strong, weak, noise), baselines | P1 | 4 | yes | [~] | `eval/cases.yaml` holds the demo pair (`btk-ms-demo`), three retrospective cases of the same class with their recorded outcomes (evobrutinib, fenebrutinib, tolebrutinib; the optional `set` and `outcome` fields) and the smoke case, each fact with its address. `eval/sensitivity.yaml`: five named documents for BTK inhibitor x multiple sclerosis (#105); run with the real model on 2026-10-10: 3 of 5 passed, the noise rule now treats drift with the later cutoff as drift (`docs/eval.md`, section 9). | Backtests on the current code; bare-LLM baseline and closed-book probe; the hand-labelled sample for the judge; repeated runs for stability; a sensitivity base whose balances are not at the ceiling and whose cutoff equals the recompute's; the other regression cases (each fact to verify). |
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
executive verdict, modeled ranges, translation chain, claim drill-down and open questions;
the gates list, ranked questions and the rNPV tornado, and the trace screen (B12) with the cost and the
calls of a run, are built.

| Milestone | Meaning | Who | Status / remaining |
|---|---|---|---|
| M0 | Contracts, fixtures and fakes merged; both start parallel work | both | [~] Contracts, fakes, the Divarasib fixture, collection, API and CLI are merged. Open: HRO761 fixture, reason-side graph nodes, the second machine. |
| M1 | `llm.call` works for one provider; extraction switches from `FakeLLM` to real | Dasha delivers, Arsenii switches | [~] The LLM layer has two adapters and extraction is wired to it in the live run; single requests to the gateway were probed, and every prompt is sized to the gateway's request and output limits. Whole runs were made on the gateway on 2026-10-10. Open: the Anthropic adapter has not carried a whole run. |
| M2 | **Bundle handoff:** a real bundle for divarasib from real connectors passes the bundle contract test; reasoning runs on it | Arsenii delivers, Dasha consumes; short pairing session | [~] Live collection → frozen bundle → reasoning is integrated and merged. Real bundles exist for BTK inhibitor x multiple sclerosis (156 to 161 evidence items) and reasoning ran on them. Open: the divarasib bundle named here; the pairing session. |
| M3 | **Walking skeleton:** one asset end to end (low quality is fine); both UIs show real data; recompute works at least as "re-run reason and score on bundle v2" | both | [~] One asset runs end to end on fixtures and, with a stand-in model, on real sources; the evidence UI runs on the API; the report screen shows the verdict, the chain and the claims with their quotes; recompute re-runs reasoning on bundle v2 and the diff screen shows it. A real-model run reaches a verdict with all steps completed. Open: a `full` recompute with a real model; the screens looked at on a live run (Report, Compare and Trace were, on 2026-10-10). |
| M4 | Eval run, leakage probe, calibration of thresholds; fix the worst failures | both, joint | [~] The eval and sensitivity runners are merged; the worst failures of the first live run are fixed. Open: both runners on a real model, real cases (B10), closed-book leakage probe, baseline, calibration. |
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
