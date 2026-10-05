# Scoring and verdict logic

The verdict is computed by deterministic code from the claim ledger. The LLM never produces the verdict, the probabilities or any number the verdict depends on. This makes runs reproducible and lets us explain exactly why a verdict changed.

All numeric weights below are **starting heuristics**. They are calibrated on the eval set (see [`eval.md`](eval.md)) and recorded in `config/scoring.yaml` with the date and reason for each change.

## Layer 1: Kill criteria (gates)

Any triggered gate caps the verdict. Gates read claims, not free text.

| Gate | Condition | Effect |
|---|---|---|
| G1 | No link of the human translation chain is supported | cap at Conditional (Do Not Invest if also G3) |
| G2 | Critical safety signal in human data | Do Not Invest unless a documented mitigation exists |
| G3 | Same target failed in this indication and the asset shows no stated difference | Do Not Invest |
| G4 | Efficacious exposure not achievable safely in humans (per supported claims) | Do Not Invest |
| G5 | Population or endpoint cannot be defined from the bundle | cap at Conditional |
| G6 | Critical unknown with no plan to resolve it (no diligence route) | cap at Conditional |

Gates fire only on claims with sufficient confidence (threshold `T_gate`, TODO). Each fired gate lists the claims that triggered it.

## Layer 2: Claim confidence

Evidence levels and weights (heuristic):

| Level | Weight |
|---|---|
| human_genetics | 0.90 |
| human_interventional | 0.85 |
| human_observational | 0.55 |
| animal_in_vivo | 0.35 |
| in_vitro | 0.20 |

For each independent group `g` supporting a claim, take the strongest evidence level, multiply by freshness, and combine:

```
support = 1 - prod_g (1 - w_g * fresh_g)
contra  = same formula over contradicting groups
confidence = support * (1 - 0.7 * contra)
```

- `fresh` decays with the age of the evidence (parameters per evidence type, TODO).
- Repeated reports of the same result share an `independence_group` and count once.
- A claim with no verified evidence is `inferred` with confidence capped at 0.3.
- Effect: one in vitro contradiction barely moves a claim backed by human genetics, while a strong clinical contradiction moves it a lot. Both behaviors are required tests.

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

1. Any gate with effect "Do Not Invest" fires: **Do Not Invest**.
2. Else any gate with effect "cap at Conditional" fires: at most **Conditional**.
3. Else if rNPV P50 >= `T_invest` and confidence of critical claims >= `T_conf` and no uncovered critical unknowns: **Invest**.
4. Else if rNPV P90 <= `T_floor`: **Do Not Invest**.
5. Else: **Conditional**, listing the conditions.

Thresholds `T_gate`, `T_invest`, `T_conf`, `T_floor` are set after running the eval set, not before. Expect most outputs to be Conditional or Do Not Invest; a verdict distribution that is mostly Invest is a calibration bug.

## What would change our mind

For each verdict, the report lists concrete conditions that flip it (for example "if Phase 2 response rate falls below X or discontinuation due to adverse events exceeds Y, the verdict becomes Do Not Invest"). These are generated from the gates and the tornado, not free text.

## Diligence questions

Ranked by value of information: how much the verdict or rNPV would change depending on the answer, weighted by how likely each answer is. Each question states what would answer it: proprietary data, patient-level data, KOL interview, experiment, CMC or IP diligence.

## Calibration protocol

1. Run the eval set (see `eval.md`) and plot the distribution of verdicts.
2. Compare verdicts and top risks with the recorded public-signal expectations.
3. Change thresholds or weights in config only with a logged reason.
4. Re-run the full eval after every change to prompts, weights or gates (regression test).
