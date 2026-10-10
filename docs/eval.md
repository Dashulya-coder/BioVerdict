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

`eval/cases.yaml` schema (`eval/cases.py`; the fields `set`, `outcome` and `probes` are optional, so an older file still loads):

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
  probes:                            # sensitivity tests (section 7)
    - { kind: strong, direction: lower, as_of: 2025-12-16, note: "...",
        evidence: { text: "<verbatim>", url: "https://...", source: "...",
                    source_kind: company, level: human_interventional, published_at: 2025-12-15 } }
  recorded_by: Dasha
  recorded_at: 2026-10-10
```

The cases in the repository are a reading of the public record by a person, each fact with the address it came from; none is an expert's answer. The demo pair is `btk-ms-demo`: a BTK inhibitor in multiple sclerosis, entered as an indication and a mechanism, no drug name. It is a class with mixed phase 3 results (fenebrutinib and remibrutinib beat teriflunomide in relapsing MS; evobrutinib and tolebrutinib failed; the FDA refused tolebrutinib in non-relapsing secondary progressive MS), a recognised liver risk, and no approval yet. The three backtests (`evobrutinib-2023-11`, `fenebrutinib-2025-10`, `tolebrutinib-2025-12`) are dated before the readout whose result is recorded as the `outcome`; judge the argument and the risks, not only the verdict (section 5).

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
| Sensitivity (strong, weak, noise) | done (live mode) | a `probe` adds one real document to the case's first finished run (`pipeline/recompute.py`) and code judges the diff of the two runs (`eval/sensitivity.py`). strong: the verdict, or a key claim's confidence by at least 0.10, or a gate moves in the stated direction. weak: the verdict and the gates hold and some confidence moves that way by at least 0.02. noise: nothing moves (verdict, gates, chain, no claim added or removed, every confidence within 0.02). The 0.10 and 0.02 are placeholders. A probe whose run could not be made is `not run`, never a pass. Fixture mode cannot run them: a recompute needs a model |
| Closed-book leakage probe, bare-LLM baseline | not done | needs paid calls to a model without retrieval and a way to score its answers |

`uv run bioverdict warm --list <file>` fills the retrieval cache for a list of assets and prints
which ids were confirmed and how much each source returned (see the [runbook](runbook.md)).

## 8. Results

Live runs of 2026-10-10 on the public sources and the team gateway (`gpt-6.1-sol` writes, `gpt-6-astra` judges), one run per case, `LLM_MAX_CONCURRENCY=3`, `RUN_TIMEOUT_S=900`. One run is not a measure of stability. Raw outputs: `eval/results/<date>/` (not committed).

| Case | Verdict | Expected | As expected | Quotes present | Sources in catalog | Sections | Judge confirmed | Time | Cost |
|---|---|---|---|---|---|---|---|---|---|
| btk-ms-demo | Conditional | Conditional | yes | 84/84 | 43/43 | 6/6 | 78 of 100 links | 262 s | $0.86 |
| tolebrutinib-2025-12 | Conditional | Conditional or Do Not Invest | yes | 60/60 | 32/32 | 6/6 | judge version 1, see below | 291 s | $0.96 |

Sensitivity, `tolebrutinib-2025-12` (a base run at 2025-12-01, one document added to it):

| Probe | Result | What happened |
|---|---|---|
| noise (a divarasib result) | **pass** | after the classify prompt was told to leave other drugs and diseases unmatched: nothing moved. Before that it added a claim about divarasib |
| strong (the PERSEUS failure, from Sanofi's release of 2025-12-15) | **fail** | the model wrote two new claims (the failure, and that Sanofi will not file for primary progressive MS) and linked no existing key claim, so no confidence and not the verdict moved. Whether a primary progressive failure should move the verdict for relapsing and secondary progressive MS is arguable; K1 needs the same indication |
| weak (Sanofi's impairment test) | **fail** | one new claim, no confidence moved lower |

What the runs showed, beyond the table:

- **The demo pair resolves with an assumption.** Open Targets 26.09 has no `multiple sclerosis` term to search for (its search returns the subtypes, not the disease: `MONDO_0005301` and `EFO_0003885` both come back null), so the indication is recorded as "not confirmed: no matching disease term" and the run goes on with the name. The BTK target resolves.
- **The report's "top risks" are generic for the demo.** They are the gate and key-claim texts ("a link of the translation chain is missing", "a key claim rests on too little evidence"), not the risks a person would name (liver injury, no approval, mixed phase 3 results). Those are in the claims and the Chair's questions, not in the three lines the summary shows. The shared-words hint against the expected risks is 0 for that reason.
- **The judge, version 1, read each quote alone and removed 71% of the links** (59 of 83), mostly fragments of a results record (the name of an endpoint, the groups, the figures), none of which says the result by itself. Version 2 reads the quotes of one claim together and removed 22% (22 of 100). The 22 left were read: quotes that name an endpoint without a result, or that belong to another drug.
- **The pipeline needs time and room.** At the old 420 s deadline the judge and the Chair were skipped on this class; at 900 s they run. The Skeptic and the Chair prompts did not fit the gateway's 16,000-character request with 70 claims (now shortened by importance), and so did the classify prompt (now the claims are shortened before the new evidence is turned away). With six reasoning modules in parallel the gateway answered 429 `concurrency_limit`; a client-wide cap (`LLM_MAX_CONCURRENCY`) and not opening the breaker on a rate limit fixed it.
- **Classify-mode recompute adds claims more readily than it moves them.** A decisive document became new claims that no gate or key claim reads. The demo script's "a strong result flips the verdict" holds on the prepared fixture and has not been shown on a live class run.

Not done: the closed-book leakage probe and the bare-LLM baseline (paid calls to a model without retrieval, and a way to score its answers), the hand-labelled sample for judge agreement, three repeated runs for stability.
