# BioVerdict project review and recommendations

Review date: 2026-10-07. Reference: all existing documents in `docs/`, including all nine ADRs, plus `README.md` and `CONTRIBUTING.md`. Implementation reviewed: backend, frontend, fixtures, compatibility script, and CI.

This is a review, not an implementation change. No application code, tests, configuration, existing documentation, or fixtures were edited for this review. This file is the sole project artifact added by the review; verification artifacts were directed to `/tmp`.

The workspace changed during inspection: the initial ClinicalTrials.gov changes were committed as `7a26139`, and untracked `connectors/pubmed.py` and `tests/connectors/test_pubmed.py` appeared. Those PubMed files were inspected and included in the final checks. Findings describe that working-tree snapshot, including work in progress; they are not a claim that the unfinished features are supposed to be complete already. Suggested owners follow `docs/work-plan.md` and are recommendations, not task assignments.

## Overall assessment

BioVerdict has a coherent design and useful, tested backend foundations, but it is currently a collection of components rather than an operable underwriting application. The main delivery gap is the missing path from user input through retrieval, freezing, reasoning, verification, scoring, and report presentation. The main correctness gap is that several of the documented trust guarantees are weaker in code than the documentation implies.

Keep the frozen evidence bundle, explicit basis/status labels, deterministic scoring, SQLite, and provider abstraction. The next work should connect these pieces and close the trust gaps before expanding the number of reasoning agents or adding infrastructure.

The largest risks are future information leaking into historical runs, claims passing a quote-presence check without support for their meaning or numbers, loss of treatment-arm identity during result extraction, critical claims being removed from scoring because of presentation limits, and spending/deadline limits that do not enforce their documented guarantees.

## What is already working

- Models distinguish evidence levels, source quality, claim basis, statuses, gates, and diligence types. Separating `registry_record` from clinical findings is particularly useful.
- Evidence freezing assigns stable IDs, applies the date filter before status supersession, computes canonical hashes, and preserves earlier evidence versions. Reload detects changes to hashed evidence.
- ClinicalTrials.gov retrieval supports pagination, stopped-study searches, posted results, retries, caching, and sponsor aliases. The new PubMed connector provides literature retrieval with fixture tests.
- Reasoning has schema validation, exact quote checks, restricted gate/claim types, explicit missing translation links, and a trace of removed content.
- Scoring implements confidence, service flags, gates, verdict mapping, and seeded PoS sampling. Missing valuation already prevents `Invest`.
- The LLM layer handles schema retries, classified errors, caches, circuit breakers, per-run accounting, and failover flags. Authentication errors do not silently fail over.
- Lockfiles are committed and CI checks both backend and frontend.

## Verification performed

| Check | Result | Scope |
|---|---|---|
| Backend pytest | **359 passed in 1.11 seconds** | Existing tests, including the in-progress PubMed tests |
| Backend Ruff lint | Passed | `ruff check --no-cache .` |
| Backend Ruff formatting | Passed; 85 files already formatted | `ruff format --check --no-cache .` |
| Dependency compatibility | **17/17 passed** | Imports, local DAG, SQLite WAL, TestClient, offline SDK construction, NumPy |
| Frontend ESLint | Passed | Existing starter application |
| Frontend TypeScript | Passed | Both app and Vite configuration checked with emission/incremental writes disabled |
| Frontend Vite build | Passed | Output directed to `/tmp/bioverdict-review-frontend-build` |
| Additional offline probes | Reproduced the issues described below | In-memory data, fake providers, mock HTTP, temporary SQLite databases |

Observed runtimes: Python 3.14.2, Node 24.21.0, pnpm 12.9.1. The compatibility check reported SQLite 3.51.2 and the expected installed backend package versions.

The sandboxed pytest and compatibility runs stalled inside the in-process Starlette/AnyIO TestClient. Both completed outside the sandbox after approval. This was an execution-environment limitation, not an application test failure.

No paid model calls, live biomedical retrieval, browser interaction, dependency upgrades, or production deployment were performed. Passing tests prove the existing tested behavior; they do not prove scientific accuracy, live provider access, complete source coverage, or an end-to-end product flow. Selected primary references were checked for SDK retry behavior and the genetic-support benchmark; the other biomedical events, model prices, and benchmark tables were not comprehensively revalidated.

## Priorities and suggested ownership

**P0** means fix or complete before demonstrating the affected trust/product guarantee. **P1** means needed for the documented useful MVP. **P2** means subsequent robustness, generality, or operating improvements. These priorities are for this review and do not redefine the work plan's original task priorities.

Evidence labels below: **Reproduced** = confirmed with an offline probe; **Observed** = directly visible in source; **Planned gap** = documented feature currently missing; **Design issue** = contract/behavior needs clarification.

| ID | Priority | Recommendation | Evidence | Suggested owner |
|---|---|---|---|---|
| R01 | P0 | Connect one complete fixture-backed workflow | Planned gap | Both |
| R02 | P0 | Enforce claim verification and rejection policy | Reproduced / design issue | Dasha |
| R03 | P0 | Stop backdating current registry content | Reproduced | Arsenii |
| R04 | P0 | Preserve result-arm identity and study context | Reproduced / observed | Arsenii |
| R05 | P0 | Preserve all decision-critical claims | Reproduced | Dasha |
| R06 | P0 | Deduplicate findings and enforce independent confirmation | Reproduced / observed | Both |
| R07 | P0 | Define translation-link polarity and aggregation | Reproduced / design issue | Dasha |
| R08 | P0 | Preserve errors and missing-data reasons | Reproduced | Both |
| R09 | P0 | Separate live retrieval from cache replay | Reproduced | Arsenii |
| R10 | P0 | Reserve spending before dispatch | Reproduced | Dasha |
| R11 | P0 | Account for paid adapter failures | Reproduced | Dasha |
| R12 | P0 | Enforce a deadline across the entire run | Reproduced / observed | Both |
| R13 | P1 | Validate bundle integrity at every consumption boundary | Reproduced | Arsenii |
| R14 | P1 | Include provenance in evidence identity | Reproduced | Arsenii |
| R15 | P1 | Improve query coverage and disclose truncation | Reproduced / observed | Arsenii |
| R16 | P1 | Validate citations against the evidence actually shown | Reproduced | Dasha |
| R17 | P1 | Version claims, links, reports, and verification | Observed / planned gap | Both |
| R18 | P1 | Make the scoring contract require current verified inputs | Observed | Both |
| R19 | P1 | Constrain numeric configuration and label PoS assumptions | Reproduced / design issue | Dasha |
| R20 | P1 | Implement or explicitly defer financial outputs | Planned gap | Dasha |
| R21 | P1 | Build the report and evidence UI around decision explanations | Planned gap / observed | Both |
| R22 | P1 | Implement the documented full-reasoning recompute fallback | Planned gap | Both |
| R23 | P1 | Implement source authority and comparable-fact conflict rules | Planned gap | Both |
| R24 | P1 | Wire configuration and independent provider fallback | Observed / planned gap | Dasha |
| R25 | P1 | Add evaluation and trust-boundary regression checks | Observed / planned gap | Both |
| R26 | P1 | Make docs describe current readiness and one consistent policy | Observed / design issue | Both |
| R27 | P2 | Establish clear SQLite job and concurrency behavior | Planned gap / observed | Arsenii |
| R28 | P2 | Harden the future user-evidence ingestion path | Planned gap | Arsenii |
| R29 | P2 | Turn domain packs into configuration and test generality | Planned gap | Dasha |
| R30 | P2 | Finish operating procedures, attribution, and licensing | Observed / planned gap | Both |

## Detailed recommendations

### R01 — Connect one complete fixture-backed workflow

**Evidence:** `backend/src/bioverdict/__init__.py:1` only prints a greeting. `backend/src/bioverdict/api/main.py:1` provides only `/health`. `frontend/src/App.tsx:1` is the Vite starter. There is no application resolver, pipeline graph, report builder, or implemented run API. Only mechanism and translation reasoning modules exist. `docs/work-plan.md` defines M0 and M3 as runnable integration milestones.

**Recommendation:** Finish one offline path: input → fixture resolver → fake collection → freeze → reason → verify → score → persisted report → API/UI. Bind all calls to one `run_id`. Make the CLI really parse `run --asset ... --as-of ...`, and wire `USE_FIXTURES` explicitly. Add real retrieval/provider calls after that path works. Keep unimplemented sections visible as `not_searched`.

**Acceptance:** One documented command and one UI action produce a report for divarasib, show the bundle hash and sources, and permit claim-to-evidence drill-down. A fixture run needs no API keys and makes no external calls.

### R02 — Enforce claim verification and rejection policy

**Evidence:** `reasoning/grounding.py:186` turns an unsupported `extracted` claim into `inferred` while keeping its text and `found` status. `ground_draft` validates the existence of an evidence ID and quote substring, but not the catalog, numbers in the claim, semantic support, or allowed identifiers in claim text. A probe accepted “The drug benefits 99% of patients” with the quote “The study is recruiting participants.” An empty catalog did not prevent acceptance. A fabricated claim whose only link failed survived with confidence 0.3. There is a `Verifier` protocol but no verifier implementation.

**Recommendation:** Require deterministic source/catalog, quote, identifier, and extracted-number checks before a claim can participate in scoring or appear as supported prose. Add the different-provider entailment judge promised by the docs. Keep unsupported hypotheses in a separate explicitly unsupported output if needed; do not preserve failed factual assertions by merely relabeling them. Distinguish supporting evidence from evidence that contradicts a proposition: a contradiction-only link does not make the proposition an extracted fact.

Resolve the policy disagreement first: `CONTRIBUTING.md` and the README say failed claims are dropped, architecture gate 3 allows a hypothesis downgrade, and ADR-002 permits an inferred downgrade. Verification must finish before the final verdict is released; dropping or downgrading a claim requires rescoring.

**Acceptance:** Valid but unrelated quotes, fabricated percentages/IDs, contradiction-only citations, and failed source checks cannot produce supported extracted claims or influence a favorable verdict. Every rejection is logged with its reason.

### R03 — Stop backdating current registry content

**Evidence:** `connectors/clinicaltrials.py:154` dates the current brief summary and primary outcomes using the study's **first** posting date. `parse_results:258` dates the current result payload using its **first** results posting date. Both payloads can contain amendments. A synthetic record first posted in 2020 and updated in October 2026 retained its new summary, endpoint, and amended result in a 2021 run. Filtering on an incorrectly assigned date cannot prevent that leakage.

**Recommendation:** Attach the availability date of the actual document revision. Prefer archived/history snapshots when available through a supported retrieval method. When only the current payload is available, use a conservative revision date and mark historical coverage incomplete if the older text cannot be recovered. Request the revision fields needed for result dating. Add stable keys for amended summaries/endpoints where appropriate. Apply the same distinction between first publication and content revision to PubMed abstracts and other mutable sources.

The PubMed connector's `_entrez_date` is an indexing date; store/label it separately from publication and revision dates rather than calling all three `published_at`. Document how early-online, indexing, and later correction dates affect visibility.

**Acceptance:** A later amendment never appears before it was available. Historical and current runs can differ in content, not only in which whole records survive a date filter. Unrecoverable historical content is reported as a gap.

### R04 — Preserve result-arm identity and study context

**Evidence:** `connectors/clinicaltrials.py:210` removes group IDs from groups, measurements, and analyses. A probe with group order `[Drug, Placebo]` but measurement order `[Placebo, Drug]` produced two values with no way to map them back to arms. The current raw result fixtures are already projected to reduced fields and do not exercise this relationship. `parse_results:247` labels every posted outcome `human_interventional` without consulting study type. The requested fields omit important outcome descriptions, denominators, safety data, and analysis context.

**Recommendation:** Preserve group IDs and measurement/analysis references, titles/descriptions, sample sizes, units, population, time frame/data cutoff, and comparison direction. Derive evidence level from the actual design; observational results must not become interventional evidence. Distinguish randomized controlled results from small uncontrolled trials when assigning evidential strength. Retrieve or explicitly mark missing adverse-event and discontinuation data, because safety is required for K2.

Use representative source-shaped fixtures containing IDs and reordered measurements. Keep a link to the raw response and the exact extracted field path so generated JSON fragments are auditable.

**Acceptance:** Values remain attached to the correct arm after input reordering. HR direction and analysis population are explicit. Observational and single-arm data cannot acquire RCT strength merely because they have registry results.

### R05 — Preserve all decision-critical claims

**Evidence:** `reasoning/grounding.py:239` keeps `critical=True` on only the first four marked claims, across modules. Soft sparse/contested gates and the key-claim confidence requirement only consider the remaining critical claims. A probe with four strong key claims followed by a contested low-confidence fifth claim returned `Conditional` before capping and `Invest` afterward. Module order can therefore affect whether a material uncertainty matters.

**Recommendation:** Separate a display limit from decision relevance. Preserve every materially critical claim for scoring; limit only the executive summary. Determine required decision dimensions in code so the model cannot avoid a weak area by omitting `critical`, adding filler claims first, or moving claims between modules.

**Acceptance:** Reordering or adding harmless earlier claims does not remove a material risk, clear S2/S3, or enable `Invest`.

### R06 — Deduplicate findings and enforce independent confirmation

**Evidence:** `scoring/confidence.py:81` does not deduplicate links passed directly to scoring. Three identical links raised confidence from roughly 0.769 to 0.891 and fired K4 in a probe. Grounding deduplicates per draft claim, but callers of `rescore`/`claim_confidence` can bypass it. Even distinct fragments from one group can exceed 0.85, so the threshold alone does not implement the documented need for independent confirmation.

The connectors also use inconsistent independence identities: ClinicalTrials.gov uses `sponsor:<name>`; PubMed uses `trial:<NCT>` or `paper:<PMID>`. A registry result and its paper can count as independent despite sharing one dataset. Different papers from one lab can count independently when no trial ID is present.

**Recommendation:** Deduplicate at the scoring boundary. Introduce dataset/finding identity and consistent sponsor/lab lineage across connectors. Consolidate repeated presentations of one result before applying diminishing weights to genuinely additional evidence. If hard gates require a second independent source, enforce that condition explicitly; define documented exceptions for authoritative direct evidence if desired. Keep mixed supporting/contradicting findings visible rather than blindly discarding one direction.

**Acceptance:** Duplicating a link, adding another excerpt of the same result, or retrieving its publication from a second source does not inflate certainty or independently satisfy a hard gate.

### R07 — Define translation-link polarity and aggregation

**Evidence:** `scoring/verdict.py:48` uses the maximum confidence of any claim attached to a chain link. Confidence measures belief in a claim's text, which can assert either that the link exists or that it fails. There is no structured polarity on the chain assertion. A probe adding a separate weak/unknown patient-benefit claim to a strong positive chain left `Invest` unchanged because the positive maximum won.

**Recommendation:** Define one canonical positive proposition per link and attach supporting and contradicting evidence to it. Alternatively, add a validated assertion polarity and a documented aggregation rule. Aggregate relevant evidence and uncertainties for the link; do not choose whichever individual sentence has the highest confidence. Show contested links separately.

The product of five heuristic confidence scores is specified in the docs, but it is not automatically a calibrated probability of clinical translation. Label it as a modeled chain score unless calibration and dependence assumptions justify stronger language.

**Acceptance:** Strong contradictory evidence lowers the appropriate chain score and can fire S1/S3. A high-confidence statement that a link fails cannot strengthen the chain. Equivalent claim orderings produce the same result.

### R08 — Preserve errors and missing-data reasons

**Evidence:** `reasoning/grounding.py:71` maps any section state other than `not_searched` to `none_found`. A probe with `mechanism=error` produced an unknown claim with `none_found`. `not_reported`, `incomplete`, and `conflicting` distinctions are also lost. `Connector.fetch` returns only a list; ClinicalTrials.gov stores failures in mutable `problems`, which is not part of the contract.

**Recommendation:** Carry structured section/query outcomes, attempted sources, omissions, and errors through collection, bundle, claims, and report. Propagate an error as an error, and absence of posted results as `not_reported`. Define how multiple upstream statuses combine. Return problems per fetch rather than relying on connector-global state. Honor status and basis constraints at the scoring boundary so an unknown cannot become established merely by carrying links.

**Acceptance:** A failed request, a skipped source, an empty successful search, and an existing study without published results produce distinguishable outcomes and appropriate diligence/retry actions.

### R09 — Separate live retrieval from cache replay

**Evidence:** `store/http_cache.py:1` says entries never expire; `connectors/http.py:59` always returns an existing entry. A mock endpoint changing its revision was called once across repeated fetches. No refresh or bypass path exists. This prevents ordinary fresh collection from discovering changed trial status, results, or newly indexed literature.

**Recommendation:** Support explicit replay, normal live retrieval, and forced refresh. Keep replay deterministic with pinned response/bundle identifiers; give mutable live sources a refresh policy and retain prior snapshots. Expose cache mode and actual fetch time in the trace/report. Do not solve this by deleting all cache data before each run.

**Acceptance:** Replay reproduces the previous bundle, while live refresh retrieves new evidence and creates a new bundle without destroying older snapshots.

### R10 — Reserve spending before dispatch

**Evidence:** `llm/budget.py:24` checks only money already spent. Spending is charged after completion, with no reservation. A call costing $0.00035 was allowed under a $0.00020 cap, as also intentionally permitted by the current budget test. Concurrent calls can all pass the check and independently overshoot.

**Recommendation:** Atomically reserve a conservative request cost before dispatch, including input tokens, bounded output, and planned retries. Reconcile reservations with actual usage and release unused capacity. Share the budget across all steps/providers of a run. When remaining budget is insufficient, use a documented cheaper setting or return an explicit incomplete outcome.

Where exact billed cost cannot be guaranteed in advance, distinguish estimated dispatch limits from actual incurred cost and use provider spending controls when available. Do not describe a post-call stop as a strict hard cap.

**Acceptance:** Two simultaneous calls cannot both consume the same remaining allowance, and a call whose bounded cost exceeds available funds is not dispatched under the claimed cap policy.

### R11 — Account for paid adapter failures

**Evidence:** `llm/providers/anthropic.py:92` raises for refusal, truncation, or missing parsed output before returning usage. An SDK stub returning 100 input/50 output tokens and no parsed output caused three retries but recorded zero tokens and zero spend. SDK parsing can also raise validation errors before the client sees a response. The client correctly charges invalid JSON returned by `FakeProvider`, but that test path does not cover these real-adapter failure paths.

**Recommendation:** Preserve raw usage and executing-model metadata for every billable response, even when parsing or acceptance fails. Charge before interpreting stop reasons/schema validity, or attach usage to typed failure results that the client always reconciles. Log individual attempts as well as call totals so fallback spend is not attributed entirely to the last provider/model. Record provider request IDs; treat usage for transport failures as unknown if it is genuinely unavailable.

**Acceptance:** Invalid parsing, refusal, and output truncation retain known usage in both budget and trace. The same stub response cannot be retried three times while reporting zero incurred cost.

### R12 — Enforce a deadline across the entire run

**Evidence:** `llm/budget.py:38` starts the clock at the first model call, excluding resolver/retrieval time. `LLMClient.call` returns cache hits before checking the deadline. `_ask_model` checks before dispatch but does not reject a response arriving after expiry. A fake clock advanced 100 seconds during a call with one second remaining, and the client returned success and subsequently a cache hit. The Anthropic adapter uses SDK retries, which can compound request timeouts. SDK timeout retries are documented in the [official Python SDK reference](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python).

**Recommendation:** Start a run deadline when the job is accepted, pass its remaining time to every retrieval/model/retry step, and check completion. Bound retry backoff and total elapsed time rather than assuming one SDK timeout covers every retry. Support cancellation of active work. Define whether a completed recorded report can be retrieved after expiry separately from whether expired execution can continue. Avoid blocking synchronous model calls on the API event loop.

**Acceptance:** Slow collection plus model retries stays within the configured whole-run timeout or ends with a persisted partial/timeout result. No new computation continues past expiry.

### R13 — Validate bundle integrity at every consumption boundary

**Evidence:** `store/models.py:248` is a normal mutable Pydantic model with mutable evidence/list/dict fields. A frozen bundle's evidence could be changed without updating its recorded hash. `load_bundle:43` checks evidence/status content but loads the catalog independently; replacing the stored catalog with `[]` passed integrity verification. `ModuleReasoner.reason` accepts arbitrary bundles without integrity validation. The divarasib fixture still has `sha256:pending-A3-freeze`, and the fixture tests do not recompute its hash.

**Recommendation:** Validate unique IDs, actual content hash, exact catalog derivation, temporal visibility, and run association before reasoning/verifying a bundle. Make snapshot data immutable or pass defensively copied validated values; freezing only the outer object is insufficient. Rebuild/compare the catalog rather than trusting independent stored JSON. Generate a real fixture hash and test it.

The current hash exclusion of bundle `as_of` is documented, and prompts include the analysis date. Preserve that distinction while recording date/configuration separately in the run identity.

**Acceptance:** Mutated content, missing/extra catalog entries, duplicate IDs, invalid hashes, and mismatched run IDs are rejected at consumption. All committed fixture bundles have recomputable hashes.

### R14 — Include provenance in evidence identity

**Evidence:** `store/evidence_ids.py:17` identifies duplicates using only URL, locator value, and excerpt. A new record with identical text but a different publication date was discarded in a probe. Changes in level, source kind, independence group, status key, or locator type can also be lost although they affect eligibility, confidence, and supersession.

**Recommendation:** Define document revision identity separately from text/finding identity. Preserve meaningful changes in provenance/date/classification as new append-only revisions, while preventing repeated retrieval of the same revision from creating duplicate evidence. Avoid identity rules that depend on arbitrary arrival order.

**Acceptance:** A corrected evidence date or classification survives as a new revision and can affect the next bundle; an identical re-fetch does not. Earlier bundles remain reproducible.

### R15 — Improve query coverage and disclose truncation

**Evidence:** `clinicaltrials.build_queries:283` searches only the named drug when `known_assets` is populated, including its stopped-study query. The divarasib probe did not search stopped programs for the broader target/indication, although K1 requires failed analogs. Asset-only searches are not indication-scoped. Page/result/measure limits silently omit additional records. Result selection is by NCT order. PubMed's `build_terms:166` restricts target-only queries to clinical trials, so indication+mechanism queries can miss genetics and preclinical mechanism evidence. PubMed limits searches without exposing total hits or date-scoping the search itself.

**Recommendation:** Separate asset evidence, same-target/same-indication analogs, competition, and mechanism/genetics queries. Use resolver aliases/IDs and explicit relevance validation. Apply historical cutoff criteria at search time as well as post-fetch to avoid recent records crowding out historical ones. Rank results by relevance/design/recency rather than identifier order. Return truncation/skipped-result reasons; use `incomplete` when bounded retrieval prevents adequate coverage. Retain useful scientific corrections/retractions as warnings even if they are excluded from positive-evidence weighting.

**Acceptance:** Known-asset and mechanism-only inputs both retrieve the evidence needed for their gates. A capped search cannot be presented as an exhaustive `none_found` result.

### R16 — Validate citations against the evidence actually shown

**Evidence:** `reasoning/prompts.py:76` omits evidence to meet a character budget and says omitted items cannot be cited. `reasoner.py:65` nevertheless validates against the full bundle. A fake model cited an omitted ID when `max_evidence_chars=0`, and the reasoner accepted it. The existing truncation test checks that omitted IDs are reported, not that they cannot be used.

**Recommendation:** Record the exact evidence subset supplied to each call and use that subset for draft grounding. Make omitted coverage visible in section status. Reserve space by module and decision relevance, including adverse evidence and important registry status; global level ordering alone can hide a decisive status record. Calculate the limit from the configured model's context budget, including instructions/schema/output reserve.

**Acceptance:** A model cannot cite omitted evidence, even if its ID appears in the omission notice or prior knowledge. Truncation preserves critical positive and negative evidence or explicitly reports inadequate coverage.

### R17 — Version claims, links, reports, and verification

**Evidence:** `store/migrations.py:51` gives claims a `version` column but the primary key is `(run_id, id)`; `claim_evidence` has no snapshot/version dimension. `Claim` itself has no report revision. Re-running reasoning starts IDs at `C-0001`. The schema cannot keep different texts/confidences for the same claim ID across report revisions without replacement or an additional identity scheme. No repositories persist claims, reports, or verification outcomes yet.

**Recommendation:** Agree a report/claim-snapshot version contract before building persistence and diffs. Associate every claim, link, verification result, and report with its bundle version/hash, reasoning/config version, and model trace. Define stable semantic claim IDs or explicit old/new correspondence for diffs. Store immutable prior reports rather than reconstructing them using current confidence or prompts. Use a migration; do not rewrite an applied migration.

**Acceptance:** Reports for bundle v1 and v2 can be loaded simultaneously with their own texts, links, scores, and verification records. Old reports remain unchanged after rescoring.

### R18 — Make the scoring contract require current verified inputs

**Evidence:** `contracts.py:44` describes `score(claims, links)`, but `DeterministicScorer.score:206` ignores links and trusts precomputed claim confidence. A stale or manually supplied confidence can therefore determine the verdict. `rescore` recomputes confidence but cannot ensure final entailment/source-authority verification has occurred. Scoring also lacks a validated bundle/run snapshot association.

**Recommendation:** Introduce a validated, verified claim-ledger input or make the scorer consume the bundle/evidence plus verified claims/links and compute confidence itself. Explicitly separate internal pure verdict-rule helpers from the public scoring boundary. Exclude unknown/unsupported/failed-verification assertions from established facts. Persist which verification and scoring configuration produced the result.

**Acceptance:** Removing/replacing evidence or rejecting a claim cannot leave a stale favorable verdict. The API cannot submit arbitrary confidence values as if they were verified scores.

### R19 — Constrain numeric configuration and label PoS assumptions

**Evidence:** `ConfidenceConfig`, `VerdictConfig`, and `PosConfig` accept invalid domains and relationships. Probes accepted `p0=1`, zero half-life, independence decay of 2, reversed hard/soft thresholds, zero draws, negative pseudo-sample size, and infinite financial range values. `probability_of_success:96` compounds repeated modifiers without deduplication. Its beta uncertainty uses an assumed effective sample size of 150, not sample counts from the benchmark. Non-oncology transitions are allocated by scaling aggregate transitions, not extracted area-specific observations.

**Recommendation:** Validate finite values, probability bounds, positive draw/sample/time parameters, complete weight tables, and cross-field threshold ordering. Reject duplicate modifier identities and require asset evidence eligibility for each adjustment. Label pseudo-sample size, inter-phase independence, cross-area scaling, modifier bounds, and probability cap as modeling assumptions. Preserve source URLs, document/version, table/figure, and extracted values for every prior; connect the chosen stage/area to resolved evidence.

The [Minikel et al. primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11096124/) supports an overall 2.6x relative-success estimate but states that effects vary by phase and therapy area. Its oncology somatic-evidence discussion differs from a universal germline adjustment. Use matched evidence or clearly label a broad fallback assumption; do not automatically treat any cancer mutation as justification for the same multiplier. Current public priors may also postdate a historical `as_of`; record a deliberate policy for prior-version leakage.

**Acceptance:** Invalid settings fail at configuration load. PoS ranges display their assumptions and applicable sources, repeated evidence/modifiers cannot inflate PoS, and historical use of later benchmark information is explicit.

### R20 — Implement or explicitly defer financial outputs

**Evidence:** There is no rNPV/capital/time-to-milestone implementation. `DeterministicScorer` accepts an externally supplied rNPV range; the verdict cannot independently establish K5 or positive economics. `VerdictResult.pos`, capital, and time fields are not populated by current scoring. `docs/scoring.md` and the demo expect these outputs; the work plan schedules finance later than the initial scoring task.

**Recommendation:** Initially preserve the honest `Conditional` outcome when valuation is unavailable. For the financial milestone, implement a seeded distribution-based model with explicit source/assumption inputs, conditional development costs, launch timing, remaining exclusivity, pricing analogs, population/uptake, discounting, and sensitivity outputs. Use the same draws for before/after comparisons. Record provenance and units for capital/time designs. Do not put a fabricated positive range into the live path just to enable `Invest`.

**Acceptance:** Missing finance is visible. A funded model produces reproducible P10/P50/P90 values and sensitivities; deterministic examples validate discounted cash flows and K5. Capital/time inputs distinguish sourced observations from assumptions.

### R21 — Build the report and evidence UI around decision explanations

**Evidence:** The frontend has no BioVerdict screens or API client. `score_verdict:173` uses critical claim texts as fallback top risks, which can present favorable facts as risks. `what_would_change_our_mind` does not generate reversal conditions for a fired hard gate. `diligence_questions` is never populated, despite explicit unknown claims.

**Recommendation:** Implement the documented input/resolver, progress, executive verdict, claim/evidence drill-down, translation chain, trace/cost, and diff views. Show source/basis/status badges and visible uncertainty. Generate risk labels from adverse assertions/gates/uncertainties; generate conditions for both fired and near-miss gates. Turn unknowns into diligence questions using their data type; defer numerical value-of-information ranking until there is a model to justify it. Explain every cap and missing financial input.

Use the work plan's feature folders and stable response models. Connect development origins through a Vite proxy or narrowly configured API CORS. Cover loading, empty, partial, failed, and reconnect states as actual product behavior.

**Acceptance:** A reviewer can navigate recommendation → claim → quote → source, see why the verdict is capped, and see what observation could change it. Positive claims do not become “risks” simply because they are critical.

### R22 — Implement the documented full-reasoning recompute fallback

**Evidence:** Bundle versions and `rescore` exist, but no add-evidence endpoint, report diff, dependency-aware recompute, or UI exists. `DraftClaim` has no `depends_on` field, so current reasoning cannot populate the documented dependency graph. Recomputing existing links alone cannot discover a newly relevant opposing result. `docs/work-plan.md` explicitly permits full reasoning on v2 as the A7 fallback.

**Recommendation:** Implement that fallback first: validate/ingest evidence → freeze v2 → rerun reasoning → verify → rescore → persist report v2 → compare with v1. Match claims semantically or with stable IDs, not list position. Explain changed evidence, claims, gates, and financial outputs. Add synthetic/source labels to controlled injections. Optimize selective recompute only once dependencies and equivalence against full recompute are tested.

For before/after historical comparisons, create separate runs when moving `as_of` backwards: `freeze` deliberately prohibits reversing the date within one run.

**Acceptance:** Strong counter-evidence changes the relevant conclusion, weak evidence has a proportionate effect, unrelated evidence changes nothing material, and the diff names the cause while preserving both reports.

### R23 — Implement source authority and comparable-fact conflict rules

**Evidence:** `docs/sources.md` requires family precedence, endpoint/population matching, and later data-cutoff comparison. Current evidence has free-text `source_family`, excerpt, and a single date, but no structured outcome/population/cutoff identity. Confidence applies a quality multiplier, which is not the same as field-specific authority. `latest_wins` only handles identical `status_key`s.

**Recommendation:** Keep source authority, document recency, and finding comparability separate. Record the minimum structured fields needed to recognize whether two numbers refer to the same endpoint, arm, population, and cutoff. Apply field-specific source rules and retain unresolved conflicts. Do not equate a terminated single study with cancellation of the whole asset, or a registry recruitment fact with proof of efficacy failure; require the gate's actual asset/indication/mechanism conditions.

**Acceptance:** Cross-trial numbers are not silently treated as head-to-head comparisons. Genuine conflicts remain visible. A source-quality weight cannot substitute for verification that a claim asserts the correct gate fact.

### R24 — Wire configuration and independent provider fallback

**Evidence:** `llm/config.py:78` reads budget/timeout environment values but ignores documented `LLM_PRIMARY` and `LLM_FALLBACKS`. There is no application settings/bootstrap loading the root `.env` and configuring DB/cache paths/providers. Default fallback stays within Anthropic, and the circuit breaker is provider-wide, so an outage can make all configured real alternatives unavailable. The different-provider judge is a TODO. Only Anthropic has a real adapter.

**Recommendation:** Build one settings/bootstrap entrypoint with explicit environment loading/path behavior and validate required configuration for the selected mode. Wire fixture/live modes and model chains from real config. Add one independent provider adapter and the judge contract; do not add all providers merely for breadth. Log requested and executing model plus effective parameters, pricing/config version, and fallback cause. Specify whether same-provider refusal fallback and provider-wide outage fallback are distinct policies. Include fallback-chain/config identity in cache policy so changed fallback settings do not silently reuse an old alternative answer.

**Acceptance:** Changing configured model chains changes runtime behavior, `.env` setup works from the documented working directory, fixtures need no secrets, and an unavailable primary provider can actually reach a tested independent fallback. Offline SDK construction is not presented as proof of live model access.

### R25 — Add evaluation and trust-boundary regression checks

**Evidence:** The repo has substantial unit tests, but no `eval/cases.yaml`, evaluation runner/results, or demonstrated pipeline integration. There is no reasoning-network import enforcement test despite the docs claiming one. Existing tests explicitly bless inferred downgrades, order-based critical capping, and budget overshoot. Fixture tests validate shapes/catalog membership without validating their hash. CI does not run the compatibility script or evaluation.

**Recommendation:** Add focused regressions for R02–R19, a fixture pipeline integration test, and meaningful live smoke tests kept separate from ordinary offline CI. Enforce that reasoning business logic cannot retrieve evidence through network imports/tools; allow only the centralized model transport needed for LLM inference. A literal prohibition on every network byte would conflict with remote LLM calls, so document this boundary precisely.

Implement the process-quality evaluation from `docs/eval.md`: supported quotes/numbers, entailment/manual agreement, source validity, explicit unknown reasons, repeated-run stability, strong/weak/noise sensitivity, historical leakage, runtime, and incurred cost. Run a sparse asset and a second domain. Keep expected ranges rather than treating deals/market reactions as proof of the correct verdict. Save configuration, hashes, prompts/models, and raw outputs with results. Use frozen installs in CI and run `check_compat.py` there.

**Acceptance:** CI fails on the reproduced trust-boundary defects after their policies are settled, and an evaluation report provides measured results instead of TODO targets. Offline component tests and live end-to-end evidence are clearly distinguished.

### R26 — Make docs describe current readiness and one consistent policy

**Evidence:** README/work-plan checkboxes remain blank despite implemented components. All ADRs remain `Proposed`. The CLI shown in README/runbook is not implemented. The stack/ADR describe React 19.3 and TypeScript 7, while package.json declares React 19.2 and TypeScript 6. ADR-008 mentions `package-lock.json` while the project uses pnpm. Verification rejection policies disagree across docs (R02). Some architecture wording assumes a completed service rather than a target design.

**Recommendation:** Separate implemented, partially implemented, and planned capabilities. Update milestone/task status from demonstrable behavior, not file existence. Document the actual working commands/toolchain and retain the tested frontend versions unless an upgrade has a concrete need. Reconcile claim rejection, “no network,” independence, date/version, and budget definitions. Keep ADR acceptance for the actual team decision process; do not mark them accepted automatically during cleanup. Record observed versions/date and a code-freeze deadline when agreed.

**Acceptance:** A new teammate can run the current project using the docs and accurately identify what the demo can do. No capability is described as implemented without a working path or check.

### R27 — Establish clear SQLite job and concurrency behavior

**Evidence:** WAL and busy timeout are configured, but tests only verify these settings, not concurrent reader/writer behavior. The schema has no foreign keys linking runs/bundles/evidence/claims. A probe froze a bundle for `R` while the runs table stayed empty. Version allocation reads the prior version before obtaining a write reservation. HTTP cache commits on the caller's connection. In-memory LLM budgets/deadlines do not survive a process restart.

**Recommendation:** Keep SQLite and the in-process job approach for the hackathon. Define connection ownership and short transaction boundaries; avoid running synchronous work on the event loop. Serialize version allocation per run or reserve the SQLite write transaction before reading the next version. Introduce appropriate run/link constraints through migrations when run creation is wired. Keep cache writes separate from evidence transactions. Persist job states/events and terminal outcomes; on startup, recover or clearly mark interrupted jobs. Reconstruct spending from persisted attempts before any restart/resume that can incur more cost.

**Acceptance:** Two writes cannot allocate the same bundle version, readers see consistent reports during work, unrelated cache writes do not commit an evidence transaction, and restart behavior is predictable. No Redis/Postgres migration is required for this scope.

### R28 — Harden the future user-evidence ingestion path

**Evidence:** The proposed `POST /runs/{id}/evidence` accepts URLs or text, and the demo includes judge-supplied documents. This route is not implemented, so the following are implementation requirements, not findings of an existing exposed vulnerability. The prompt uses a document delimiter but interpolates source metadata directly and still relies on model obedience for semantic behavior.

**Recommendation:** When implementing ingestion, validate supported source/URL types, redirects, size/time limits, and public destinations; prevent the server fetching local/private network endpoints. Keep pasted/synthetic/user-provided text distinguishable from independently fetched authoritative documents. Escape or serialize source metadata in prompts, and subject adversarial document instructions to the same grounding/entailment policy as normal content. Prevent arbitrary input from assigning its own authoritative source kind or independence identity.

**Acceptance:** Invalid or misleading provenance cannot acquire regulator/RCT authority. User-supplied content has a visible origin and controlled retrieval behavior, and instructions inside it do not bypass verification.

### R29 — Turn domain packs into configuration and test generality

**Evidence:** `docs/domain-pack-oncology.md` describes a configurable domain pack and second-domain smoke test. No playbook/config implementation exists. Reasoning currently has two generic module instructions; no resolver or ontology-based selection exists. PubMed and registry searches depend heavily on names and target symbols.

**Recommendation:** Put disease-specific endpoint/design/analog checklists in explicit configuration, selected by resolved IDs, with a generic fallback. Test indication+mechanism, drug name, and company code inputs, including ambiguous aliases, multiple targets, sparse evidence, and an unfamiliar non-oncology mechanism. Keep assumptions visible when normalization cannot establish identity. Extend actual source connectors in the work plan's order; raw Open Targets fixtures alone do not provide live Open Targets access.

**Acceptance:** A second-domain input completes without prompt rewrites or manually injected disease facts, and ambiguous names do not silently resolve to the wrong program.

### R30 — Finish operating procedures, attribution, and licensing

**Evidence:** `docs/runbook.md` includes placeholder doctor/run/warm/eval commands. The documented reset command targets a relative `data/` path whose meaning depends on current directory. Demo recordings, measured cost/time, source terms/attribution, code-freeze date, organizer requirements, and repository license remain TODO. The source plan PDF cited by scoring/models is not present in the supplied docs, so that external contract could not be independently checked.

**Recommendation:** Add operating commands only once implemented; make storage paths consistent and reset behavior explicit for an initialized runtime database. Prepare one replayable report/diff and one tested live path, record hashes/config/commit, and rehearse source/provider outage and partial-run behavior. Measure median/p90 time and cost from actual attempts, including failed paid outputs. Confirm demo duration and hidden-query formats. Resolve the already documented attribution/licensing requirements before public release; add a stable reference to the source plan if the team is allowed to retain it.

**Acceptance:** A teammate can start, diagnose, replay, back up, and recover the demo with the runbook, and quoted performance numbers come from saved runs. Publication prerequisites already identified in the project docs are resolved.

## Recommended implementation order

1. **Agree the trust policies and wire a fixture run.** Resolve R02/R07/R26; implement R01 with versioned response contracts. Show unavailable finance honestly.
2. **Close the data/scoring failure modes.** Fix historical dating and result context (R03/R04), critical selection and independence (R05/R06), statuses and bundle validation (R08/R13/R14), and current verified scoring (R18).
3. **Make live execution bounded and repeatable.** Implement cache modes and accurate spend/deadlines (R09–R12), settings/provider behavior (R24), and query/subset coverage (R15/R16).
4. **Finish the demonstrable report and evidence-change flow.** Add versioned persistence, UI/explanations, recompute/diff, source authority, and financial outputs as capacity permits (R17/R20–R23). Prioritize the work plan's full-reasoning fallback over selective dependency optimization.
5. **Evaluate, record, and freeze.** Complete R19/R25, a sparse case, a second-domain smoke test, and operating rehearsal. Address concurrency/ingestion requirements when wiring those features. Defer extra agents, more providers, market sentiment, broad IP/CMC automation, and infrastructure expansion until the main path has measured quality.

## Minimum acceptance checklist for a credible demo

- [ ] A real CLI/API/UI path completes a fixture run, and one deliberately selected live path has been exercised.
- [ ] Every supported conclusion opens a verified quote and source; rejected factual claims do not survive as softened supported prose.
- [ ] Historical runs exclude later revisions, and unavailable historical data is visible.
- [ ] Clinical numbers retain endpoint, arm, population, units, design, and cutoff context.
- [ ] Critical risks and contradictory evidence cannot disappear through claim order, duplication, or prompt truncation.
- [ ] Missing evidence, failed retrieval, and unsearched sections remain distinguishable.
- [ ] Every released verdict uses the current verified ledger and records configuration/bundle identity.
- [ ] Spend and timeout behavior matches the stated policy, including retries and failed paid responses.
- [ ] New evidence produces preserved before/after reports and a causal diff; strong, weak, and irrelevant cases have been checked.
- [ ] Unimplemented valuation and uncalibrated scores are labeled honestly rather than shown as established asset probabilities.
- [ ] Process-quality evaluation and measured cost/time results are saved and reproducible.

No recommendations in this file have been implemented as part of this review.
