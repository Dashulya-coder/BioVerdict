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

`eval/cases.yaml` schema:

```yaml
- id: divarasib-2026-10
  input: { asset: divarasib }
  as_of: 2026-10-06
  expected_verdict: [Conditional, Invest]
  expected_top_risks: ["competition from approved KRAS G12C inhibitors", "..."]
  signals:
    - { text: "...", url: "...", date: "..." }
  recorded_by: Dasha
  recorded_at: TODO
```

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
| Verdict stability | done | same verdict and mean Jaccard overlap of the top-risk lists, between repeats in which a model answered afresh. Repeats served from fixtures or from the model cache are shown as `replayed`: clear `CACHE_DIR/llm` (or use a new one) to measure stability |
| Verdict distribution, time, cost | done | from `runs` and `llm_calls`; fixture runs cost nothing and take no time |
| Post-cutoff leakage | done | citations the model proposed and code could not ground, and the claims dropped for it. Every one is a row in `verification_log` |
| Expected verdict | done | the verdict is one of `expected_verdict`; an empty list means no expectation |
| Expected top risks | hint only | each expected risk beside the reported risk that shares most words with it. A person has to read both |
| Citation support rate, judge agreement | not done | needs the entailment judge (B8) |
| Sensitivity (strong, weak, noise) | not done here | `pipeline/recompute.py` and `GET /runs/{id}/diff` are the interface for B10 |
| Closed-book leakage probe, bare-LLM baseline | not done | needs paid calls to a model without retrieval and a way to score its answers |

`uv run bioverdict warm --list <file>` fills the retrieval cache for a list of assets and prints
which ids were confirmed and how much each source returned (see the [runbook](runbook.md)).

## 8. Results

| Case | Verdict | Expected | Top risks match | Citation support | Time | Cost |
|---|---|---|---|---|---|---|
| TODO | | | | | | |

Raw outputs: `eval/results/<date>/`.
