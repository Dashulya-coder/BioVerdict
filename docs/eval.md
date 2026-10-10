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
| Judge agreement | agreement between the judge and ~30 manually labelled claims | TODO |
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
| Judge agreement | not done | needs a hand-labelled sample of about 30 claims |
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
The runner (`bioverdict sensitivity`, `eval/sensitivity.py`) reads only that diff:

| Kind | Passes when |
|---|---|
| strong | the named module's balance moves in the expected direction and the document is listed among its causes |
| weak | the same, and the answer and the verdict do not change and the balance moves by at most 0.15 |
| noise | the document is placed on no claim and no answer or verdict changes |

No model grades a result. The expected direction of each case is what a reader of the sentence
would expect, recorded before the run.

**Dataset items** (`eval/sensitivity.yaml`; verbatim sentences of public records the connectors
retrieved on 2026-10-10, for BTK inhibitor x multiple sclerosis):

| Case | Kind | Item | Expected |
|---|---|---|---|
| strong-tolebrutinib-not-superior | strong | PMID 40202623, tolebrutinib vs teriflunomide in relapsing MS | clinical development down |
| strong-evobrutinib-not-superior | strong | PMID 39307151, evobrutinib vs teriflunomide in relapsing MS | clinical development down |
| strong-fenebrutinib-lesions | strong | PMID 40683275, fenebrutinib vs placebo, new T1 Gd+ lesions | clinical development up |
| weak-microglia-preprint | weak | bioRxiv doi 10.64898/2026.08.25.747169, laboratory work on microglia | mechanism up, a little |
| noise-kras-lung-release | noise | Roche release of 2026-07-02 on divarasib in lung cancer | nothing moves |

**State.** Run once with the real model on 2026-10-10 (section 9): 3 of 5 cases passed, and two of the three failures say more about the benchmark than about the system (below).

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

**A base run with an earlier cutoff** (`--as-of 2024-06-30`): 46 evidence items (the run of today has 171), Conditional (0.52), 61 claims, judge 25 links judged and 4 removed. Registry results are dated by the last update of the record, so far fewer trial results are seen: the benchmark below runs on this thin base.

**Sensitivity benchmark** on that base (`bioverdict sensitivity`, five documents added one at a time; recompute cutoff 2026-10-10):

| Case | Result | What happened |
|---|---|---|
| strong-tolebrutinib-not-superior | pass | clinical development balance +1.00 to +0.68, the document named as the cause |
| strong-evobrutinib-not-superior | pass | clinical development +1.00 to +0.69, named |
| strong-fenebrutinib-lesions | **fail** | the document is a cause of no module: placed on no claim that a module reads. The balance was already at its ceiling (+1.00) |
| weak-microglia-preprint | **fail** | mechanism balance +1.00 to +1.00. The document is named as a cause, but a balance at the ceiling cannot move up |
| noise-kras-lung-release | pass (after a change of the rule) | by the first rule it failed: the unmet-need module changed its answer, with no cause. It did so in all five cases, the noise one included: the base is as of 2024 and the recompute as of 2026, and the evidence aged. A module that moves with no cause is now reported as drift, not failed; a module the document is a cause of, or the verdict, still fails the noise case |

What it means for the benchmark: the two failures that are not the system's are the ceiling (a balance at +1.00 cannot show an expected rise; the base should be one where the balances are not saturated, or the weak case should expect no move) and the cutoff (a base and a recompute two years apart drift together). The benchmark has never been run with the cutoff of the base equal to that of the recompute, which would need documents dated before the base.

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

**Not done:** the backtests (`evobrutinib-2023-11`, `fenebrutinib-2025-10`, `tolebrutinib-2025-12`) have not been run on the current code; the closed-book leakage probe and the bare-LLM baseline (paid calls to a model without retrieval, and a way to score its answers); the hand-labelled sample for judge agreement (31 of 70 links removed here, 13 of 72 in the run Arsenii measured: whether either is right needs a person); three repeated runs for stability.
