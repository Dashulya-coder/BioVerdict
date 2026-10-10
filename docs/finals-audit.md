# Finals audit: BTK inhibitor × multiple sclerosis

> **Status on merged `main` (after #105 and #106, 2026-10-10).** This audit was written by a
> second coding agent against an earlier commit, while #105 was in progress. Read it with these
> corrections:
>
> - Fixed with this document: findings 1 and 2 (recompute), 7 (arm ids in registry results),
>   8 (results dated by the record's last update) and the silent truncation of finding 9.
> - Fixed by #105: preprints are read by the mechanism module; a failed judge request no longer
>   cancels the whole check (finding 3 is otherwise open: unanswered links are still kept);
>   the work-plan snapshot (finding 17).
> - Decided otherwise (finding 4): for a question with no drug, PoS **stays** computed from
>   the leading program of the class, stated as an assumption. Choosing an asset from the
>   landscape is offered on the resolved-input screen as a next step, not required first.
> - The stored-run table below lacks the third run (5 min 7 s, verification and Chair completed).
> - Reference links: the Sanofi, EMA and two Roche pages and both PubMed records were opened and
>   name what the table says; the NEJM page refuses automated access and was not checked.
>
> Everything else below is as the audit found it and is open.

Audit date: 2026-10-10. Baseline: `2e3807e`, with read-only inspection of the active
working directory and its stored runs. No open PRs were returned at the start of the audit.
No paid model calls were made for this audit. Local tests use fake models and sources.
The concurrent working directory must not be overwritten: it contains newer gateway,
verification and sensitivity-runner work, which is distinguished below from this baseline.

## Product decision

Confirmed with the user: **indication + mechanism → class landscape → user selects an
existing asset → asset-specific underwriting in the selected indication**. An idea with
no identifiable asset is a landscape/gap result, not the primary investment use case.
The asset, disease subtype, geography and evidence cutoff belong beside the conclusion.
Do not treat the furthest-developed member's phase as the phase of an unnamed investment.
(Later the same day the user chose to keep the class PoS with its assumption stated; see the
status note above.)

## Rubric alignment

Each row carries 5 points for contradictory evidence, 5 for the evidence trail and 5 for
output quality. These are readiness observations, not predicted judges' scores.

| Module | A: changed answer and its cause | B: recommendation → claims → evidence → sources | C: BTK × MS quality |
|---|---|---|---|
| Disease and unmet need | Balance/diff implemented; no measured module-specific intervention | Claim drill-down implemented | Guidelines returned no extracted facts in both inspected completed runs; MS subtype/standard-of-care coverage needs review |
| Mechanism and biological validation | Evidence confidence and module balance implemented | Implemented; database association is not directional causal evidence | Preprints were collected but excluded by module filters at baseline; concurrent work addresses this |
| Preclinical → human translation | Links and confidence changes implemented | Implemented | Must distinguish CNS exposure, engagement and patient benefit, and avoid combining different drugs into one successful chain |
| Clinical development | Incremental classification, gates and diff implemented; synthetic unit tests exist | Implemented | Study design is not efficacy; RMS, nrSPMS and PPMS findings need separate interpretation |
| Competitive + commercial | Combined module and diff implemented | Qualitative claims traceable; financial assumptions have a separate path | Target-class analogs omit much of indication-level competition; MS market coverage and payer evidence are incomplete |
| Investment underwriting | Reports deterministic verdict and causal claims | Gates/critical claims traceable; rNPV inputs are not fully in this claim trail | No selected asset at baseline; PoS uses stage/area priors, rNPV uses uncalibrated assumptions |

UI already provides input, resolver, six module cards, evidence/source inspection, Compare,
report and trace. A visible asset-selection step, clear landscape labeling, verification
coverage and a rehearsed BTK comparison are still needed. One overall verdict flip satisfies
the minimal demo sentence; it does not establish contradictory-evidence behavior in all six
separately scored modules. A module answer or materially changed explanation can be the change;
forcing every document to flip the overall investment verdict would be a mistake.

## Findings and priorities

### P0: demo correctness

1. **Full recompute excluded analyst additions.** `reasoning/prompts.py` filtered
   `analyst_added` out of every module's source families. Fixed in this audit: additions
   retain their provenance and are available to every module, with the existing prompt budget.
   Regression cases cover all six reasoning modules, with and without batching.
2. **Incremental new claims bypassed the initial citation rejection policy.**
   `classify_evidence.py` retained a new claim after one of its citations failed grounding,
   including an unsupported inference. Fixed: reject that entire new claim and its links,
   log `claim_dropped`, and preserve the original run and pre-existing claims.
3. **Verification currently fails open.** `pipeline/reason_score.py:verify_pass` keeps
   links when the judge fails; unanswered judgments also retain links. A report with a
   successful quote check can therefore have no semantic verification. The newer concurrent
   implementation judges decision-bearing claims in independent batches, but still retains
   unanswered links. Before presenting a report as verified, require successful checks for
   the claims that decide its recommendation, or expose an explicit unverified state and
   prevent those claims deciding it. Coordinate this with the active verification changes.
4. **A pair is currently underwritten as a class.** `run_financials` uses the leading
   class phase when no asset was selected. This is not asset underwriting. Implement the
   product decision above and preserve indication/mechanism when restoring or selecting a run.
5. **An added fact cannot generally resolve a gap in incremental mode.** The classifier
   links to an `unknown`/`hypothesis`, but confidence stays at the unsupported default;
   every new claim is grounded as `CLINICAL` and loses translation-chain placement. Use
   the repaired full recompute when evidence establishes a new module fact or closes a chain
   gap. A robust incremental extension needs explicit claim replacement/routing and review
   of the shared contract; adding a link alone is insufficient.
6. **Real contrary findings are not always logical contradictions.** The existing weak/
   strong unit tests link a cell experiment or later PFS finding against a historical ORR
   claim. Those test arithmetic, not medical entailment. A later negative trial can undermine
   a development thesis without making an earlier measured outcome false. Match asset,
   population, endpoint, comparator and timepoint before asserting contradiction.

### P1: medical and numerical fidelity

7. **Registry results lose treatment-arm identifiers.** `_outcome_fragment` retains a list
   of arm titles but drops group ids from measurements and analyses. Order alone cannot
   reliably attribute a number to a treatment, especially with missing measurements.
   Preserve the ids and their title mapping in the source excerpt.
8. **Time-travel is not a historical database.** Trial protocols are conservatively dated
   by last update, but `parse_results` dates the current results text by *first* posting.
   Amended results can therefore leak into an earlier cutoff. Use the latest record update
   conservatively, and prefer same-cutoff document ablations for the finals demonstration.
   Resolver lookups are also current snapshots. An `as_of` flag does not remove model memory.
9. **Retrieval truncation is partly silent.** ClinicalTrials.gov page and result-study caps
   stop retrieval without adding `problems`; the final outcome-measure cap also drops text.
   Report these as incomplete coverage. The prompt's 600-character prefix can omit the
   endpoint, denominator or decisive clause even when its evidence id is counted as read.
10. **Clinical inputs are not yet sufficient for trustworthy kill criteria.** K4 accepts
    a terminated study as a program stop; K2 accepts a hold/boxed warning as evidence for
    unmitigable on-target toxicity. Neither implication is generally valid. Guards check
    keywords/source kinds, not whether the whole gate proposition is established. Human
    review and negative controls should cover business stops, ended studies with continuing
    programs, lifted holds, mitigated toxicity and failed superiority versus an active control.
11. **Source count is not independent replication.** Multiple excerpts from one trial
    receive diminishing additional weight; a press release and a paper can describe the same
    dataset. Analyst additions group by hostname, which neither deduplicates a study across
    publishers nor distinguishes independent studies in one journal. Avoid inflating certainty
    or a hard-gate decision by republishing a result.
12. **Investment outputs remain heuristics.** `financial_model` calls PoS with stage and
    therapy area, without the evidence modifiers or sparse-evidence setting. Changing an
    efficacy claim need not change PoS/rNPV. K5 is disabled for uncalibrated negative rNPV,
    but a positive placeholder rNPV can help allow Invest. Report this asymmetry and calibrate
    it before asserting valuation quality. The class phase is not a substitute for asset stage.
13. **Retrieval scope has large MS gaps.** Approved analogs are selected by target, which
    can import oncology BTK labels/prices while omitting competing MS therapies. SEC matching
    depends on sponsor names; EMA and current sponsor releases are not general live sources.
    Geography-specific regulatory status, MS subtype prevalence, eligible population, net
    price, treatment duration and deal terms must be sourced or explicitly unknown.

### P2: reliability, cost and clarity

14. **Report length and confidence need calibration.** Module balance counts each claim;
    splitting one finding into several claims can change the balance. Deduplicate by finding
    and trial, cap repeated contributions and test paraphrase/splitting invariance. The
    product of translation-link confidences assumes an independence structure that is not
    validated; display it as a heuristic, not a calibrated probability of clinical success.
15. **Avoid unnecessary computation and calls.** Cache deterministic financial calculations
    by bundle hash plus configuration; report and financial endpoints recompute them. Reserve
    judge budget/deadline before generating extra claims, bound concurrency globally across
    runs, and prioritize decisive complete passages. Do not trade semantic verification for
    a larger report. HTTP cache refresh is already configurable; enable it deliberately for
    current-status work and freeze it for controlled comparisons.
16. **Restart recovery is limited.** FastAPI background tasks live in one process. A crash
    can leave a run `running`; add startup reconciliation or a resumable job boundary before
    relying on unattended operation. Check malformed SSE `Last-Event-ID` handling and remove
    abort listeners after each frontend polling delay. Neither requires a new service stack.
17. **Documentation is ahead of and behind the code.** Work-plan snapshot says no measured
    whole run, despite stored completed runs; several ADR checkboxes and runbook descriptions
    are stale. Distinguish intended architecture, implemented features, measured behavior and
    remaining work. Do not infer readiness from a checkbox or an empty Results table alone.

## Stored-run evidence, without a new paid run

Read-only sample from `backend/data/bioverdict.sqlite`, completed BTK × MS runs:

| Run | Seconds | Claims | Quotes present | Entailment results | Verdict |
|---|---:|---:|---:|---|---|
| `R-367b1e5e637e4dcebfb91ab440d69ecb` | 224.92 | 76 | 23/23 remaining links | 18/93 judged links confirmed; 51 claims downgraded | Conditional |
| `R-6b2d82e341a44b8196c6b877e1a2b20d` | 441.44 | 100 | 111/111 | Judge skipped: `AllModelsFailedError` | Conditional |

These runs precede concurrent fixes and do not measure this audit branch's live quality.
They establish why quote presence and six-section coverage alone are inadequate metrics.
The first confirmation fraction is **not** a hallucination rate: neither the judge nor the
individual rejections have been validated by human annotation. The second run's 100% quote
presence is **not** 100% citation support. Logged provider cost is an estimate, not invoice cost.

## Medical reference set for the finals

These are named source items to review and freeze, not invented expert verdict labels.
Access checked 2026-10-10. Do not hard-code their conclusions into prompts.

| Item | What an evaluator must distinguish | Primary source |
|---|---|---|
| HERCULES, tolebrutinib, NCT04411641 | nrSPMS disability progression and hepatic safety; does not establish efficacy in all MS | [Trial publication](https://www.nejm.org/doi/full/10.1056/NEJMoa2415988) |
| GEMINI 1/2, PMID 40202623 | Lack of superiority to teriflunomide on ARR in RMS; not proof of no biological activity | [Publication](https://pubmed.ncbi.nlm.nih.gov/40202623/) |
| evolutionRMS 1/2, PMID 39307151 | Evobrutinib efficacy and safety; keep the asset and population explicit | [Publication](https://pubmed.ncbi.nlm.nih.gov/39307151/) |
| PERSEUS, NCT04458051 | Sponsor reports missed PPMS endpoint and no PPMS registration pursuit; not a refutation of nrSPMS findings | [Sanofi, 2025-12-15](https://www.sanofi.com/en/media-room/press-releases/2025/2025-12-15-06-05-00-3205094) |
| Cenrifki EPAR | EU authorisation on 2026-06-19 for adults with SPMS without relapses in the preceding two years, with liver monitoring; geography and eligibility matter | [EMA](https://www.ema.europa.eu/en/medicines/human/EPAR/cenrifki) |
| FENtrepid | Sponsor reports non-inferiority versus ocrelizumab; a numerical benefit does not establish superiority | [Roche, 2026-02-07](https://www.roche.com/media/releases/med-cor-2026-02-07) |
| Fenebrutinib FDA filing acceptance | Sponsor reports priority-review acceptance on 2026-09-30; acceptance is not approval | [Roche](https://www.roche.com/investors/updates/inv-update-2026-09-30) |

## Benchmark methodology and acceptance criteria

The committed `eval/cases.yaml` at baseline has one Divarasib smoke case with no expert
signals. Existing sensitivity unit tests use canned model responses. Concurrent work adds
`eval/sensitivity.yaml` and a runner; their existence is not a measured passing benchmark.

1. Freeze a development set and a held-out set with named item ids, source dates, hashes,
   model versions, prompts and scoring configuration. Register expected *direction and
   reasoning*, not an arbitrary Invest label inferred from an acquisition or market reaction.
2. For each of the six modules create a matched before/after case at the **same cutoff**,
   changing only the supplied document. Add weak, irrelevant, duplicated, wrong-population
   and wrong-endpoint controls. Disclose withholding; do not present an ablation as a real
   historical forecast. Reversing the document's polarity must change the applicable answer.
3. Use synthetic programs with novel names for controlled counterfactuals. For anonymized
   real cases redact identifiers, sponsors, dates and distinctive numerical fingerprints;
   test whether a separate closed-book identification probe can recover the identity.
   Calling a dataset anonymous does not establish that it is. A model's release date alone
   does not establish its training cutoff or lack of later updates.
4. Count all rejected and unjudged claims as well as surviving quotations. Report entailment
   coverage, human agreement on roughly 30 stratified claims, source/quote validity, module
   coverage, directional sensitivity, noise invariance, fresh-run stability, p50/p90 time
   and cost. A cached repeat measures reproducibility, not model stability.
5. Compare to a bare-LLM baseline under the same input/cutoff and a retrieval-only or simple
   evidence baseline. Mark paid model baselines and live sensitivity runs **not run** until
   authorized. Offline regression passes demonstrate software properties, not investment
   forecasting accuracy or specialist-level medical quality.
6. Rehearse the precise pair in the UI, select an asset, show all six answers, then one
   controlled evidence addition and its claim/source trail. Keep a recorded tested bundle
   for outages; label cached, synthetic and live material visibly.

## Verification

Baseline full offline backend suite: 1,063 passed. Audit regression results and the
asset-selection/source-provenance follow-ups must be recorded with their final commit and PR.
No final score, live-model quality claim or future investment return is inferred from tests.
