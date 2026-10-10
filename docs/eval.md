# Evaluation plan

Owners: Dasha owns the eval cases, expectations and sensitivity tests (task B10); Arsenii owns the eval runner, grounding metrics, leakage probe and cache pre-warm (task A8). See [`work-plan.md`](work-plan.md).

We cannot measure whether a recommendation is *right* (outcomes take years), and historical cases leak through LLM training data. So we measure **process quality**: grounding, honesty about unknowns, stability, sensitivity to evidence, and leakage. We also keep a regression set of expert-style expectations.

## 1. Leakage probe

Goal: show the system works through retrieval, not memory.

1. For each drug in the test list, ask each candidate model **without retrieval** for phase, target, competitors and recent events.
2. Score the answers against a reference built from the bundle (completeness and correctness).
3. Run the full system with retrieval on the same drugs.
4. Compare, grouped by the organizers' depth label (Emerging, Niche, Obscure, Very obscure).

Expected: the gap between closed-book and system is largest for Obscure and Very obscure drugs. Emerging drugs act as a control where the model already knows a lot.

Also test **post-cutoff leakage** in time-travel runs: count claims that are not supported by the bundle but match events after `as_of`. The quote gate should drop them; report the count.

## 2. Baselines

- **Bare LLM:** the same input prompted once, no retrieval, from each of the three providers.
- **Unobio Diligence (optional, ask organizers):** the free landscape for 3-5 drugs, compared section by section.

## 3. Metrics

| Metric | Definition | Target |
|---|---|---|
| Citation support rate | share of quoted claims where the entailment judge confirms the quote supports the claim | TODO |
| Judge agreement | agreement between the judge and ~30 manually labelled claims | 30 rows read (section 9); the judge was blind to registry numbers, fixed in A9 |
| Source validity | share of cited URLs and IDs that are in the bundle catalog and resolve | about 100% |
| Quote presence | share of claims whose quote appears verbatim in the evidence | 100% after gates |
| Coverage | share of required report sections with `found` or an honest status (not silent gaps) | TODO |
| Unknown honesty | on sparse assets, share of `unknown` items with a correct status and a diligence type | TODO |
| Verdict stability | same verdict across 3 runs of the same input; Jaccard overlap of top-3 risks | TODO |
| Sensitivity (strong) | verdict moves in the expected direction when a strong counter-result is added | pass/fail per case |
| Sensitivity (weak) | a weak result lowers confidence but does not flip the verdict | pass/fail per case |
| Sensitivity (noise) | an irrelevant document changes nothing material | pass/fail |
| Verdict distribution | counts of Invest / Conditional / Do Not Invest across the set | mostly Conditional / Do Not Invest |
| Time per run | median and p90 | within the demo budget |
| Cost per run | median and p90, from the trace table | TODO |

## 4. Regression set (expert-style expectations)

We do not have the organizers' expert answers. We build 8-10 cases from public market signals and record an expected verdict and main risks, then re-run after every change to prompts, weights or gates.

Candidate cases from our plan (verify each fact by search before recording an expectation):

| Asset | Public signal to verify |
|---|---|
| Efruxifermin | acquisition of its developer by Novo Nordisk |
| Duvakitug | Sanofi-Teva partnership |
| KT-474 | Sanofi-Kymera partnership |
| Petrelintide | Roche-Zealand agreement |
| MariTide | market reaction to Phase 2 data |
| Divarasib | Phase 3 head-to-head readout (2026-07) |
| HRO761 | Phase 1 data, resistance reports |
| Zoldonrasib | Breakthrough designation (2026-01), Phase 3 start |

A deal or market reaction is a noisy proxy for an expert verdict. Record it as a *signal*, and write expectations as ranges ("Conditional or better") unless the signal is clear.

`eval/cases.yaml` schema (`eval/cases.py`; `set` and `outcome` are optional, so an older file still loads):

```yaml
- id: tolebrutinib-2025-12
  set: backtest                      # demo | regression | backtest | smoke   (default: regression)
  input: { asset: tolebrutinib }     # or { indication: ..., mechanism: ... } or { query: "..." }
  as_of: 2025-12-01
  expected_verdict: [Conditional, Do Not Invest]
  expected_top_risks: ["Drug-induced liver injury", "..."]
  signals:
    - { text: "...", url: "...", date: "..." }
  outcome:                           # a backtest: what happened after as_of; never shown to the model
    { text: "...", url: "...", date: 2025-12-15 }
  recorded_by: Dasha
  recorded_at: 2026-10-10
```

The cases in the repository are a reading of the public record by a person, each fact with the address it came from; none is an expert's answer. The demo pair is `btk-ms-demo`: a BTK inhibitor in multiple sclerosis, entered as an indication and a mechanism, no drug name. It is a class with mixed phase 3 results (fenebrutinib and remibrutinib beat teriflunomide in relapsing MS; evobrutinib and tolebrutinib failed; the FDA issued a complete response letter for tolebrutinib in non-relapsing secondary progressive MS, Sanofi, 2025-12-24; the EU authorised it as Cenrifki on 2026-06-19 for secondary progressive MS without relapses in the last two years, with liver monitoring, EMA, checked 2026-10-10), and a recognised liver risk. An earlier version of this paragraph said "no approval yet": that was wrong for the EU. The three backtests (`evobrutinib-2023-11`, `fenebrutinib-2025-10`, `tolebrutinib-2025-12`) are dated before the readout whose result is recorded as the `outcome`; judge the argument and the risks, not only the verdict (section 5). Sensitivity tests are a separate file, `eval/sensitivity.yaml` (section 8).

## 5. Time-travel backtesting

Historical programs with known outcomes (for example early KRAS G12C inhibitors, anti-amyloid antibodies before their pivotal readouts, CETP inhibitors) run with evidence cut off before the readout.

Limitation: models know many outcomes from training. Judge **the quality of the argument and the risks identified**, not only the verdict.

## 6. Hidden test set readiness

At the finals the organizers will enter queries whose expert analysis they already have and compare verdict, main risks and diligence questions. Practice:

- Run 5 queries you have not seen, in all input formats (indication + mechanism, drug name, company code).
- Measure time and failure modes.
- Verify short-and-correct beats long-and-wrong: the executive verdict must name the right main risk first.

## 7. The runner (A8): what is implemented

`uv run bioverdict eval --cases ../eval/cases.yaml --out ../eval/results/<date> [--repeat N]`
(code in `bioverdict/eval/`). Every number is counted by code from the stored records of the
runs; no model judges a report.

| Metric of section 3 | State | How it is counted |
|---|---|---|
| Quote presence | done | links whose quote is verbatim in the excerpt of the evidence they name |
| Source validity | partly | cited evidence whose address is in the bundle catalog; whether the address still resolves is not checked |
| Coverage | done | required sections (those the reasoning modules write) that have at least one claim, unknowns included; the collected status of every section is in `results.json` |
| Unknown honesty | partly | `unknown` claims that carry a diligence type; whether the status is *correct* needs a person |
| Verdict stability | done | same verdict and mean Jaccard overlap of the top-risk lists, between repeats that reasoned afresh: every reasoning call of the run was answered by a model, none from the cache (cached extraction is fine, it gives the same bundle). Other repeats are shown as `replayed`: clear `CACHE_DIR/llm` (or use a new one) to measure stability |
| Verdict distribution, time, cost | done | from `runs` and `llm_calls`; fixture runs cost nothing and take no time |
| Post-cutoff leakage | partly | counted: citations the model proposed and code could not ground, and the claims dropped for it (every one is a row in `verification_log`). That is an upper bound, not a measurement: a rejected citation is usually a misquote. Matching an unsupported claim to a real event after `as_of` is not done |
| Expected verdict | done | the verdict is one of `expected_verdict`; an empty list means no expectation |
| Expected top risks | hint only | each expected risk beside the reported risk that shares most words with it. A person has to read both |
| Citation support rate | partly | the judge exists (B8) and the runner reports how many judged links it confirmed; its agreement with a person is not measured |
| Judge agreement | partly | 30 rows labelled by a model and the disputed ones confirmed by a person (section 9); 16 rows where model and judge agree were not read by a person |
| Sensitivity (strong, weak, noise) | not done here | `pipeline/recompute.py` and `GET /runs/{id}/diff` are the interface for B10 |
| Closed-book leakage probe, bare-LLM baseline | not done | needs paid calls to a model without retrieval and a way to score its answers |

`uv run bioverdict warm --list <file>` fills the retrieval cache for a list of assets and prints
which ids were confirmed and how much each source returned (see the [runbook](runbook.md)).

## 8. Sensitivity benchmark (finals criterion A, per module)

**Question.** Does a module change its answer when it receives new or contradictory evidence,
does it name that evidence, and does it stay put for evidence that is weak or unrelated?

**Method.** A base run is made with an earlier cutoff, so that later publications are absent.
Each case then adds one document through the same path as the API's add-evidence route: the
model only places the document on existing claims (or writes a new fact), code grounds the
quote, recomputes every confidence and every module answer, and the diff is computed by code.
A recompute at a later cutoff also ages every claim, so a case is not compared with the base run
but with a **control**: the base run recomputed at the same cutoff with no document (one control
per cutoff, shared by its cases; code only ages and rescores, the model classifies nothing).
Control and case differ only in the document, so the diff is its effect and nothing else. The
runner (`bioverdict sensitivity`, `eval/sensitivity.py`) reads only that diff; every "before" in
its table is the control:

| Kind | Passes when |
|---|---|
| strong | the named module's balance moves in the expected direction and the document is listed among its causes |
| weak | the same, and the answer and the verdict do not change and the balance moves by at most 0.15 |
| noise | the document is placed on no claim and no answer or verdict changes (no exception for drift: against the control there is none) |

No model grades a result. The expected direction of each case is what a reader of the sentence
would expect, recorded before the run.

**Dataset items** (`eval/sensitivity.yaml`; verbatim sentences of public records the connectors
retrieved on 2026-10-10, for BTK inhibitor x multiple sclerosis):

| Case | Kind | Item | Expected |
|---|---|---|---|
| strong-tolebrutinib-not-superior | strong | PMID 40202623, tolebrutinib vs teriflunomide in relapsing MS | clinical development down |
| strong-evobrutinib-not-superior | strong | PMID 39307151, evobrutinib vs teriflunomide in relapsing MS | clinical development down |
| strong-fenebrutinib-lesions | strong | PMID 40683275, fenebrutinib vs placebo, new T1 Gd+ lesions | translation up (was clinical development up; changed 2026-10-11, reason below) |
| weak-microglia-preprint | weak | bioRxiv doi 10.64898/2026.08.25.747169, laboratory work on microglia | mechanism up, a little |
| noise-kras-lung-release | noise | Roche release of 2026-07-02 on divarasib in lung cancer | nothing moves |

**State.** 5 of 5 on 2026-10-11 with the real model (section 9), after one expectation was changed with its reason and two defects of the classification of added evidence were fixed; 3 of 5 on 2026-10-10 before that.

A time-travel comparison needs no model and no benchmark file: two runs of the same question at
two cutoffs, compared with `GET /runs/{id}/diff`, list each module before and after with the
evidence published in between.

## 9. Results

Live runs of 2026-10-10 on the public sources and the team gateway (`gpt-6.1-sol` writes, `gpt-6-astra` judges), one run each, `RUN_TIMEOUT_S=900`. One run is not a measure of stability. Raw outputs: `eval/results/<date>/` (not committed).

**The demo pair** (`btk-ms-demo`, as of the day of the run):

| Verdict | Expected | Quotes present | Sources in catalog | Sections | Claims | Judge | Time | Cost |
|---|---|---|---|---|---|---|---|---|
| Conditional (0.62) | Conditional | 89/89 | 48/48 | 6/6 | 106 (7 unknown) | 70 links judged, 31 removed, 26 claims downgraded, 42 links of context claims not judged | 357 s | $0.99 |

Modules of that run: unmet need supports (weight 0.21 for, 0.00 against), mechanism mixed, translation mixed, clinical development mixed (1.74 for, 1.79 against), competitive and commercial against, investment mixed (gates S1 and S2, PoS 47% modeled). The report's three "top risks" are the gate and key-claim texts ("a link of the translation chain is missing", "a key claim rests on too little evidence", a key claim at 30%), not the risks a person would name (liver injury, regional regulatory status, mixed phase 3 results); those are in the claims and the Chair's eight questions. The recorded expected risks therefore match by shared words at about 0.

**A run without the gateway's size limit** (`R-cf6f3be64e7b409f803f162134a0f174`, merged `main` at #122, as of 2026-10-10): Conditional (0.71), 355 s, $1.23, 214 evidence items (the collection of #118 is in it, so it is not a clean comparison with the run above), 137 claims (1 unknown). The Skeptic grounded 5 objections (0 before); the Chair read 7,810 tokens of claims (4,059 before) and asked 8 questions. The judge removed 33 of 83 links (40%), about as before: wider passages did not change it, because nearly every removal is a quote that names a registry outcome ("The quote only names the T2-lesion endpoint; it does not report the means") while the values sit elsewhere in the same record, stored as JSON with group codes. One clinical answer was cut off at the output limit and retried short.

**Results stored as lines** (`R-e0a3a432b1a6486da63da74805af1a04`, #123 and #124 together before they were merged, as of 2026-10-10): Conditional (0.67), 312 s, $1.78, 214 evidence items, 194 claims (a module may now read four batches instead of three, hence more claims and cost). The judge removed 32 of 119 links (27%, from 40%). Of the 43 links to registry results, 34 now quote a line with a value (`Tolebrutinib 60 mg: 0.17 ...`) and 5 still the measure's heading. Most removals left are of a comparison quoted with one group's value only ("The quote reports only teriflunomide's annualized relapse rate. It does not establish the comparison"): the judge is right, and the module prompt now asks for both groups' lines or the analysis line. One translation answer was cut off at the output limit. The Skeptic grounded 1 objection, the Chair asked 5 questions.

**The whole bundle read** (#125: module batches of 16,000, up to eight, at most 15 claims an answer, a module's own sources first). Two runs, as of 2026-10-10, 214 evidence items each:

| | `R-15cc9a4bd8c142be915a0fa54c0497bc` (batches of 12,000, up to four) | `R-0cb20fbb3dc443b091d01a58d9760476` (16,000, up to eight) |
|---|---|---|
| Verdict | Conditional (0.69) | Conditional (0.69) |
| Time, cost, model calls | 297 s, $1.47, 50 | 486 s, $3.07, 77 |
| Evidence left out of module prompts for length | 353 (module x item) | 0 |
| Claims | 150 | 299 |
| Registry trials cited by a claim | 4 of 11 | 11 of 11 (PERSEUS among them) |
| Drugs approved for the indication cited | 21 of 29 | 29 of 29 |
| Evidence items cited | 71 of 203 | 132 of 203 |
| Judge: links removed | 14 of 116 (12%) | 13 of 233 (6%) |
| Answers cut off at the output limit | 0 | 0 |
| Skeptic objections grounded / Chair questions | 4 / 8 | 6 / 8 |

In the first, 31 of the links to registry results quote an `Analysis of` line and 11 quote several group lines together: the rule for comparisons works. The second reads everything at twice the cost; its Skeptic answer used 3,777 of the 4,096 tokens, close to the limit, and its 299 claims weigh on the module answers, which count claims (`limitations.md`).

**The written case** (#126, the synthesis step, on the bundle and cached model answers of `R-0cb20fbb3dc443b091d01a58d9760476`). At high effort from 60,000 characters the answer was cut off at 4,096 tokens and the short retry kept one sentence a thesis (`R-86b324c4bd7e4156af8ac8cfa3cca9bf`). At medium effort from 40,000 (`R-0e5b05a835d1432297ab78cb3f46f138`): 24 sentences in the six theses, none dropped by code, 2,402 output tokens, 37 s, $0.04. The development plan takes its sequence and size from the trials in the claims (a Phase 2 of 130 participants with a placebo crossover on new active lesions, then disability progression against placebo in non-active secondary progressive MS), names the failed relapse route against teriflunomide and PERSEUS, and keeps the exposure gap open; the investment case quotes the capital and time code computed, says they rest on placeholders, and says rNPV and deal outcomes are not established. Code checks citations and numbers, not meaning: these sentences were read by us, not by a labelled benchmark.

**The verdict changes on contradicting evidence** (`eval/sensitivity-evobrutinib.yaml`, 2026-10-10). The brief asks for an example where new or contradictory evidence changes the system's conclusion. The base is the asset before its phase 3 read out: `evobrutinib for multiple sclerosis`, as of 2023-11-30 (`R-34158eeca1b34375a86331eb442e5afc`: Conditional 0.50, gates S1 and S2, 105 evidence items, 319 s, $0.94). Each case is compared with a control recompute at the same cutoff (2024-09-30) without a document.

| Case | Documents (verbatim, checked against the record) | Expected | Result |
|---|---|---|---|
| strong-evolution-phase3-failed | Merck KGaA release of 2023-12-05 ("...did not meet its primary endpoint of annualized relapse rate ... compared to oral teriflunomide in both studies") and PMID 39307151 ("The efficacy of evobrutinib was not superior to that of teriflunomide.") | Do Not Invest | **pass**: Conditional → Do Not Invest (0.86), gate K1 fired; one new clinical claim, "Evobrutinib failed the primary annualized relapse-rate endpoint versus teriflunomide in both EVOLUTION trials", cites both documents (two independence groups), confidence 0.86, both links confirmed by the judge; clinical development mixed → against |
| control-partial-hold-one-source | Merck KGaA release of 2023-04-12 (the FDA's partial clinical hold on evobrutinib) | Conditional | **pass**: one source names a risk and does not kill |

It took three runs to get there, each failure a defect fixed in the same PR: (1) the classification prompt was sized at 16,000 characters with all 88 claims in it, so both documents went unread ("2 item(s) not read"): it now has 60,000; (2) the model wrote one claim per document, each with one independence group, and tagged no gate: the classification task now says to write one claim citing every document that states the same fact and to tag a kill criterion; (3) the K1 guard did not read "was not superior to" or "endpoint was not met" as a failure for efficacy: it does now, except in a noninferiority trial, and the K2 guard no longer reads a lifted hold as a hold. The two documents report the same two trials; an added document's independence group is its web host, so they count as two groups. The trials are independent of each other, the two reports of them are not: say so on stage.

**A base run with an earlier cutoff** (`--as-of 2024-06-30`): 46 evidence items (the run of today has 171), Conditional (0.52), 61 claims, judge 25 links judged and 4 removed. Registry results are dated by the last update of the record, so far fewer trial results are seen: the benchmark below runs on this thin base.

**Sensitivity benchmark** on that base (`bioverdict sensitivity`, five documents added one at a time; recompute cutoff 2026-10-10):

| Case | Result | What happened |
|---|---|---|
| strong-tolebrutinib-not-superior | pass | clinical development balance +1.00 to +0.68, the document named as the cause |
| strong-evobrutinib-not-superior | pass | clinical development +1.00 to +0.69, named |
| strong-fenebrutinib-lesions | **fail** | the document is a cause of no module: placed on no claim that a module reads. The balance was already at its ceiling (+1.00) |
| weak-microglia-preprint | **fail** | mechanism balance +1.00 to +1.00. The document is named as a cause, but a balance at the ceiling cannot move up |
| noise-kras-lung-release | pass (after a change of the rule) | by the first rule it failed: the unmet-need module changed its answer, with no cause. It did so in all five cases, the noise one included: the base is as of 2024 and the recompute as of 2026, and the evidence aged. A module that moves with no cause is now reported as drift, not failed; a module the document is a cause of, or the verdict, still fails the noise case |

*Method note.* That run compared each case with the base, and the noise case passed only after a drift exception was added to its rule. Since then the runner compares each case with a control at the same cutoff and the noise rule has no exception (section 8); this table was not re-run with it and is kept as the record of the first run.

What it means for the benchmark: the two failures that are not the system's are the ceiling (a balance at +1.00 cannot show an expected rise; the base should be one where the balances are not saturated, or the weak case should expect no move) and the cutoff (a base and a recompute two years apart drift together). The benchmark has never been run with the cutoff of the base equal to that of the recompute, which would need documents dated before the base.

**Re-run on the current code** (after #128, 2026-10-10, with the control). Base `R-7965504f84cb411ab268aab0ab737d91` (as of 2024-06-30: Conditional 0.52, 50 evidence items, 165 s, $0.36); control `R-6cbbe927160f40a7b57e8218645ad382` (the base recomputed at 2026-10-10 with no document); the noise rule strict, without the drift exception. Results: `eval/results/2026-10-10-ms-current/`.

| Case | Result | What happened |
|---|---|---|
| strong-tolebrutinib-not-superior | pass | clinical development +1.00 to +0.45, the document named as the cause |
| strong-evobrutinib-not-superior | pass | clinical development +1.00 to +0.46, named |
| strong-fenebrutinib-lesions | **fail** (expectation) | placed as a translation claim on the biological-response link: the link went from weak to supported and translation +0.74 to +0.78; clinical development, which the case names, did not move. MRI lesions are the biological response of the brief's chain, so the system's placement is defensible; the case's expectation was written before a new fact could close a chain link (#116). Changing it needs a reason and is left to the team |
| weak-microglia-preprint | **fail** | linked to a mechanism claim that is context (`neutral`), which carries no weight in the balance: +0.51 to +0.51. Laboratory evidence weighing nothing is by design; the case expects "up, a little" |
| noise-kras-lung-release | pass | no module moved, under the strict rule |

3 of 5, as before, but each result now stands on a control at the same cutoff; the two failures are where a document was placed, not drift.

**5 of 5 on 2026-10-11.** Same base; control `R-ae67ad95e37546ca835a4df2a6485d5d`; results `eval/results/2026-10-11-ms-current/`. What changed, in order:

1. *Fenebrutinib: the expectation, with a reason.* Fewer new MRI lesions is the "biological response" link of the brief's chain, not a patient benefit (fewer relapses or less disability), so the case now expects translation up. The case had been written before a new fact could close a chain link (#116). Under the first expectation it fails; say so when the score is quoted.
2. *Microglia preprint: a path to the mechanism module.* A new claim from added evidence could only be grounded as a clinical claim or a chain link, so laboratory work on the target never reached the mechanism answer: the first attempt put it on the human biological-response link, typed "drug acts in humans". A new claim about the target's role in the disease (`target_causal`, no chain link, no gate) is now grounded as a mechanism claim, and the prompt marks neutral claims `context` (a link to one moves nothing).
3. *The question in the classification prompt.* After step 2 the fenebrutinib paper was turned away as "bearing on nothing" in 5 of 5 tries: the task told the model to set aside evidence about "another drug" but never said the report is about the class. The prompt now carries the run's resolved question, as the module prompts do. Afterwards fenebrutinib and microglia passed 3 of 3 repeats each, then the whole file 5 of 5.

| Case | Result | What happened |
|---|---|---|
| strong-tolebrutinib-not-superior | pass | clinical development +1.00 to +0.45, named |
| strong-evobrutinib-not-superior | pass | clinical development +1.00 to +0.46, named |
| strong-fenebrutinib-lesions | pass | translation +0.74 to +0.78, named |
| weak-microglia-preprint | pass | mechanism +0.51 to +0.56 (within the weak limit of 0.15), answer and verdict unchanged, named |
| noise-kras-lung-release | pass | no module moved |

The verdict case was re-run on the same code (`eval/results/2026-10-11-evobrutinib/`, control `R-f8e4a6a008724fc48f9877e5d5ff5237`): 2 of 2, Conditional to Do Not Invest (0.86) with K1 on one claim citing both documents (`R-7d76fa6cd25a423fb08ee7e11f857696`); the single-source hold stays Conditional. These cases were used to find the defects, so they are a development set, not a held-out score.

**Coverage of the medical reference set** (`docs/finals-audit.md`, "Medical reference set for the finals"; run `R-20261010-125211-cf5016`, as of 2026-10-10, one live run). This is a **development set, written by us, not held out**: it shows what the bundle and the claims contain, not how the system performs on items it has not seen. Method: each item is looked up in the run's evidence (`/runs/<id>/evidence`) by trial id, PMID or source address; an item counts as *cited* only if a claim has a link to one of its evidence records (`/runs/<id>/report`), not if the claim text happens to mention it.

| Reference item | In the bundle | Cited by a claim |
|---|---|---|
| HERCULES, NCT04411641 | 9 registry records; the NEJM paper is not among them | yes: 6 claims (C-0042, C-0043, C-0045 to C-0048) |
| GEMINI 1/2, PMID 40202623 | yes (E-0112, PubMed) | yes: 4 claims (C-0005, C-0022, C-0023, C-0071) |
| evolutionRMS 1/2, PMID 39307151 | yes (E-0111, PubMed) | yes: 4 claims (C-0004, C-0015, C-0016, C-0070) |
| PERSEUS, NCT04458051 | 3 registry records (E-0050 to E-0052) | **no: 0 claims** |
| Cenrifki EPAR (EMA) | no | no |
| FENtrepid (Roche, 2026-02-07) | no | no |
| Fenebrutinib FDA filing acceptance (Roche, 2026-09-30) | no | no |

Also checked: no evidence record and no claim mentions liver injury or hepatic safety (the system's biggest known risk for the class). 39 of the 156 evidence records are cited by any claim: registry 13 of 78, regulatory analogs 13 of 45, literature 10 of 13, preprints 3 of 4, approved analogs 0 of 8, CMS spending 0 of 4, population 0 of 3, target database 0 of 1. Six of the 11 registry trials in the bundle have no citing claim (NCT04458051, NCT04742400, NCT05064436, NCT07067463, NCT07299019, NCT07776743). Reading it: 3 of 7 items are reached by claims, 4 of 7 are absent or unused, and the three absent items are EMA and sponsor press releases, which no connector fetched in this run; the cause of the unused records (modules not given them, or a limit) is not yet checked.

**Not done:** the backtests (`evobrutinib-2023-11`, `fenebrutinib-2025-10`, `tolebrutinib-2025-12`) have not been run on the current code; the closed-book leakage probe and the bare-LLM baseline (paid calls to a model without retrieval, and a way to score its answers); the rest of the judge sample (rows 31 to 56 of `judge-sample.csv`; the 30 read are below) and a re-run of the judge on the same 30 after the fix; three repeated runs for stability.

### Judge agreement: first 30 rows of the sample (2026-10-10)

The sample is 56 (claim, quote) pairs of run `R-20261010-125211-cf5016`; rows 1 to 30 hold 13
links the judge removed and 17 it kept. **How they were labelled:** a model (not the judge's
model family; it saw the claim and the passage only, not the judge's answer) labelled all 30;
Dasha, who is not a biologist, read every row where the label differs from the judge's and
agreed or not. The 16 rows where model and judge agree were not read by a person. This is not a
gold set; it shows where the judge goes wrong, not its error rate.

| | Same as the judge | Different |
|---|---|---|
| Judge kept 17 | 13 | 4: rows 14 and 27 kept on a fact that is not the claim's point (confirmed by Dasha); rows 2 and 11 first marked `unsure`, then `supports` by Dasha (the judge was right) |
| Judge removed 13 | 2 (rows 8 and 17: a conclusion about investment from one sentence) | 11: rows 3, 4, 6, 15, 16, 18, 21, 24, 25, 29 confirmed by Dasha (the passage holds the numbers the claim quotes); row 1 is `unsure` (its conclusion is an inference, but the judge's stated reason, "no numerical result", is wrong) |

**Finding.** All 11 registry result records among the removals were judged blind. A record is
JSON in which the group names come first and the first number starts at character 440 to 495;
the judge was shown 450 characters around the quote, so it saw the groups and no values and
wrote "the quote identifies treatment groups but does not report ...". The claims were right
and were removed: 10 of the 13 removals, in the run whose "13 of 72" was read as a sign of
leniency. The numbers are checkable by eye in the file.

**Fix (A9).** A registry result record is shown to the judge as lines of text, each value beside
the name of its group, with the unit, time frame and the analyses (p-value, interval). All 36
result records of the local store render this way; the status, design and label records are not
touched. Not yet measured: the judge on the same 30 rows after the fix, and the judge on the
other 26 rows. Open on the rule, not on the reading: the judge keeps a link that supports "one
of the facts the claim asserts" (rows 14 and 27: "is a BTK inhibitor" under a claim about
lesions); whether a background fact may keep a claim's main point alive is a decision for
`verification/entailment.py`'s prompt.
