# Scoring and verdict logic

The verdict is computed by deterministic code from the claim ledger. The LLM never produces the verdict, the probabilities or any number the verdict depends on. This makes runs reproducible and lets us explain exactly why a verdict changed.

All numeric weights below are **starting heuristics**. They are calibrated on the eval set (see [`eval.md`](eval.md)) and recorded in `config/scoring.yaml` with the date and reason for each change.

## Layer 1: Kill criteria (gates)

Source of truth: the Unobio plan (PDF). The LLM only establishes a fact and attaches evidence to it; code applies the rule. Gates read claims, not free text.

**Hard (any one fires: Do Not Invest):**

| Gate | Condition | Detected from |
|---|---|---|
| K1 | The same target failed in Phase 2/3 for efficacy in the same indication, and the current program's difference is not explained (better exposure, patient selection, other modality) | AACT (`why_stopped`, results), PubMed |
| K2 | Serious on-target toxicity in humans with no way to mitigate it (clinical hold, deaths, class boxed warning) | openFDA FAERS, FDA, press releases |
| K3 | Genetics contradicts the direction of action: gene loss of function is harmful in humans and the drug mimics that loss | Open Targets, GWAS Catalog |
| K4 | The sponsor stopped the program (asset level) | ClinicalTrials.gov, SEC EDGAR |
| K5 | rNPV is negative even in the optimistic scenario (P90) | Investment model |

**Soft (any one fires, no hard gate: at most Conditional):**

| Gate | Condition | Detected from |
|---|---|---|
| S1 | A translation-chain link is missing (no human target engagement, unknown exposure in the target tissue) | Translation agent |
| S2 | Key claims carry the `sparse` flag | Evidence store |
| S3 | A key claim carries the `contested` flag | Evidence store |
| S4 | 3 or more competitors with the same mechanism are a phase or more ahead, with no clear advantage | Competition agent |
| S5 | The biomarker or endpoint is not recognised by the regulator as a surrogate | FDA guidance, trial design |
| S6 | IP protection ends soon after the expected launch, or ownership is unclear | Orange/Purple Book, patents |

A hard gate (K1-K5) fires only on a claim with confidence of at least `t_hard_gate` (0.85); a soft gate (S1-S6) fires at `t_gate` (0.6). A hard gate means Do Not Invest, so it needs more than one registry record (about 0.77 alone): a stop reason may be a business decision. A hard-gate claim between 0.6 and 0.85 does not fire, but it caps the verdict at Conditional and asks for a second independent source. Thresholds are config parameters, calibrated on the eval set. A criterion that nearly fired is recorded in `GateResult.near_miss` and becomes a line in "What would change our mind" (for example: "S4 fires if one more competitor reaches Phase 3").

## Layer 2: Claim confidence

The LLM only classifies each piece of evidence (level, direction, which claim). Code computes the confidence.

**Step 1. Weight of one piece of evidence:**

```
w_i = L(level, claim_type) x Q(source) x R(recency) x I_k
```

`L` depends on the claim type: for "the target is causal" human genetics is strongest; for "the drug works in humans" an RCT is strongest.

| Evidence level | `target_causal` | `drug_acts_in_humans` |
|---|---|---|
| human_genetics | 1.0 | 0.4 |
| human_interventional (RCT) | 0.8 | 1.0 |
| human_observational | 0.5 | 0.4 |
| animal_in_vivo | 0.3 | 0.2 |
| in_vitro | 0.15 | 0.1 |

- `Q` (source quality): peer-reviewed paper, FDA/EMA, trial registry 1.0; preprint 0.7; press release or company presentation 0.5; `ai_inference` 0.3.
- `R` (recency): biological data decays slowly (half-life about 10 years). For trial and company status only the latest record counts.
- `I_k` (independence): evidence from one lab or sponsor is sorted by weight and the k-th item gets a multiplier `0.5^(k-1)`. Five papers from one group count slightly more than one, not five times more.

**Step 2. Aggregation in log-odds:**

```
logit(c) = logit(p0) + kappa * sum_i s_i * w_i,    s_i = +1 (supports), -1 (contradicts)
```

`p0 = 0.5` by default, `kappa = 1.2` to start. Contradicting evidence may get an extra multiplier of 1.2 to offset LLM optimism. A claim with no verified evidence is `ai_inference` with low weight.

Worked example (claim "target is causal", kappa = 1.2), required as unit tests:

| Evidence state | sum(s*w) | Confidence |
|---|---|---|
| Genetics (1.0) + observational (0.5) + animal (0.3) | +1.8 | 90% |
| + weak in vitro contradiction (-0.15) | +1.65 | 88% |
| + strong contradiction: large biobank, no association (-1.0) | +0.8 | 72% |

A weak contradiction barely moves the claim; a strong one lowers it clearly. Both behaviors are required tests.

Assumptions made by the code (not stated in the plan):

- A claim of type `other` takes the weaker of the two level-weight columns per level.
- A claim with no verified evidence gets confidence 0.3 and the `sparse` flag.
- Undated evidence counts at a given `as_of` only if it was fetched on or before that date.
- Recency applies to peer-reviewed, preprint and regulator sources; registry and company records
  are not decayed because the bundle freeze keeps only the latest version of each record.

**Step 3. Service flags:**

- `sparse`: sum of |w| below a threshold. Report "too little data"; financial-model ranges widen.
- `contested`: both the supporting and the contradicting sums are strong (for example both above 0.8). Shown explicitly in the report, never averaged away.
- Translation chain: the probability of the chain is the product of the confidence of its five links. A link with confidence below 0.4 is a `missing_link`.

## Layer 3: Probability of success

```
PoS(stage -> approval) = product of remaining phase-transition probabilities
```

1. **Base rate** from public benchmarks for the therapeutic area and modality (see [`sources.md`](sources.md)). Base rates are `extracted` with a source.
2. **Modifiers**, multiplicative, bounded, each with a cited basis:
   - human genetic support for the target (relative success reported around 2.6x in Minikel et al., 2024; use the published value for the matching area and verify);
   - selection biomarker used for the population (benchmarks report roughly double LOA);
   - failure of close analogs (reference class below);
   - supported vs missing links in the translation chain.
3. **Reference class.** Analogs are chosen by weighted similarity: same target, pathway, indication, modality. Report the analog list; do not hide it.
4. Output a **range** (for example P10-P90 of PoS), never one number. The range widens when evidence is sparse.

Modifiers and their bounds live in config, are `modeled`, and show their assumptions in the report.

## Layer 4: rNPV with Monte Carlo

```
rNPV = sum_t  PoS_cum(t) * CF(t) / (1 + r)^t   -   sum_t  Cost(t) * P(reach t) / (1 + r)^t
```

Inputs are distributions, not points:

| Input | Distribution source |
|---|---|
| PoS by stage | Layer 3 range |
| Peak sales | addressable patients x price analogs x uptake range (TODO distributions) |
| Price | CMS ASP/NADAC analogs and class pricing (TODO) |
| Time to milestones | trial duration and enrollment-rate analogs |
| Capital | Layer 5 |
| Discount rate | range (TODO) |

Run N draws (TODO N, for example 10,000). Report P10 / P50 / P90 and a tornado chart showing which assumption moves rNPV most. Every input shows its assumption and label `modeled`.

## Layer 5: Capital and time to next milestone

1. Effect size and SD from prior trials on the same endpoint.
2. Power calculation gives N patients.
   - Continuous endpoint, two arms: `n per arm = 2 * (z_(1-alpha/2) + z_(1-beta))^2 * sigma^2 / delta^2`
   - Time-to-event endpoint, 1:1 randomization (Schoenfeld): events `d = 4 * (z_(1-alpha/2) + z_(1-beta))^2 / (ln HR)^2`
   - Single-arm response endpoints use a stated design (for example a two-stage design); state it.
3. Cost = N x cost per patient for the therapeutic area + overhead (TODO benchmark source).
4. Duration from enrollment rate (registry analogs) plus follow-up.

Output: a range of capital and time to the next value inflection point (for example a Phase 2 readout). Report which assumptions dominate.

## Verdict mapping

Applied in order:

1. Any hard gate (K1-K5) fires: **Do Not Invest**.
2. Else any soft gate (S1-S6) fires: **Conditional**.
3. Else **Invest** if all hold: rNPV P50 > 0, translation-chain probability >= 0.5, key claims have confidence >= 0.7.
4. Else **Conditional**, listing the conditions.

All thresholds are config parameters set after running the eval set. LLMs lean optimistic and real biotech investors are sceptical, so most outputs should be Conditional or Do Not Invest; a verdict distribution that is mostly Invest is a calibration bug. Check by running all 20 drugs from the list.

## What would change our mind

For each verdict, the report lists concrete conditions that flip it (for example "if Phase 2 response rate falls below X or discontinuation due to adverse events exceeds Y, the verdict becomes Do Not Invest"). These are generated from the gates and the tornado, not free text.

## Diligence questions

Ranked by value of information: how much the verdict or rNPV would change depending on the answer, weighted by how likely each answer is. Each question states what would answer it: proprietary data, patient-level data, KOL interview, experiment, CMC or IP diligence.

## Calibration protocol

1. Run the eval set (see `eval.md`) and plot the distribution of verdicts.
2. Compare verdicts and top risks with the recorded public-signal expectations.
3. Change thresholds or weights in config only with a logged reason.
4. Re-run the full eval after every change to prompts, weights or gates (regression test).
