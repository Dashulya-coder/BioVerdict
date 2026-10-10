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

A hard gate (K1-K5) fires only on a claim with confidence of at least `t_hard_gate` (0.85); a soft gate (S1-S6) fires at `t_gate` (0.6). A hard gate means Do Not Invest, so it needs more than one registry record (about 0.77 alone): a stop reason may be a business decision. A hard-gate claim between 0.6 and 0.85 does not fire, but it caps the verdict at Conditional and asks for a second independent source. Confidence alone is not a second source: two records of one study share an independence group and reach about 0.86, so a hard gate also needs supporting evidence from at least two independence groups (`hard_gate_min_groups`, read from `confidence_parts.independent_groups`). Only evidence that adds weight to the claim counts as a source: a record whose level weighs nothing for the claim type (a registry record under a causal claim) does not make a second group. Otherwise it is reported as not yet confirmed. Thresholds are config parameters, calibrated on the eval set. A criterion that nearly fired is recorded in `GateResult.near_miss` and becomes a line in "What would change our mind" (for example: "S4 fires if one more competitor reaches Phase 3").

**Gate guards (code).** The model tags a claim with the gate it asserts; code keeps the tag only if the cited evidence shows that kind of fact (`reasoning/gate_guards.py`). The guard is a necessary condition: scoring still weighs the claim. A removed tag is recorded as a drop of kind `gate`; the claim stays.

| Gate | The cited evidence must show |
|---|---|
| K1 | a stop for lack of efficacy: a registry `whyStopped` that reads as futility or an endpoint not met (a business, funding or enrolment stop does not count, and neither does wording that mixes the two; see `reasoning/stop_reason.py`) |
| K2 | a safety stop, a clinical hold or a boxed warning |
| K3 | human genetics (animal and in vitro evidence cannot assert it) |
| K4 | a terminated or withdrawn study, or a statement that a program was discontinued |
| S4 | at least three independent sources (competitors of one sponsor or one paper count once) |

Claims that assert a gate about a study or program are typed `study_fact` (K3 stays `target_causal`). `study_fact` is the only type a registry record can fully support, so it is allowed only in the modules that describe studies and programs, and a `study_fact` claim can never be a key (`critical`) claim: a protocol description cannot carry the verdict.

## Layer 2: Claim confidence

The LLM only classifies each piece of evidence (level, direction, which claim). Code computes the confidence.

**Step 1. Weight of one piece of evidence:**

```
w_i = L(level, claim_type) x Q(source) x R(recency) x I_k
```

`L` depends on the claim type: for "the target is causal" human genetics is strongest; for "the drug works in humans" an RCT is strongest.

| Evidence level | `target_causal` | `drug_acts_in_humans` | `study_fact` |
|---|---|---|---|
| human_genetics | 1.0 | 0.4 | 0.4 |
| human_interventional (RCT) | 0.8 | 1.0 | 1.0 |
| human_observational | 0.5 | 0.4 | 0.4 |
| animal_in_vivo | 0.3 | 0.2 | 0.2 |
| in_vitro | 0.15 | 0.1 | 0.1 |
| registry_record | 0 | 0 | 1.0 |

`registry_record` (a trial's existence, status, design or stated endpoints, not its findings) never supports an efficacy claim, so it weighs 0 for `target_causal` and `drug_acts_in_humans`. A `study_fact` claim is a fact about a study or program: a trial was stopped, a competitor is in Phase 3, the sponsor dropped the program. Those are what the gate claims (K1, K4, S4-S6) assert and what a registry establishes, so a registry record weighs 1.0 there; the other levels follow the `drug_acts_in_humans` column. Claims of type `other` take the weaker of the first two columns per level, so a registry record weighs 0 for them: it cannot support, for example, "the molecule modulates its target".

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

**Market size today (A9, `bioverdict/market/tam.py`, served by `GET /runs/{id}/market`).** Until
the Monte Carlo exists, the bundle's market records are combined by plain arithmetic:

- *Patients*, the first that the bundle has: US new cases a year of the cancer site (NCI State
  Cancer Profiles); else the CDC's measured adult prevalence times the population aged 15 and
  over; else Orphanet's point prevalence class (for the US, the world or Europe) times the whole
  US population, the class bounds giving the range.
- *Biomarker fraction*, for a cancer site only: when the asset's registry records name one
  variant of a target clearly (KRAS G12C), the new cases are multiplied by the share of patients
  with that protein change among the patients of that cancer type in the MSK-IMPACT cohort
  (cBioPortal), counted by code; the range uses the 95% Wilson interval of that share. For
  divarasib it is 194 of 1,567 patients (12.4%). No stage or line-of-therapy fraction exists.
- *Price*: Medicare's average spending per beneficiary, latest reported year, on each product
  approved against the same target (Open Targets names them): lowest, median, highest.
- *Market size*: patients times price, bound by bound.

It is the size of a market at analog prices, not a sales forecast: no diagnosis, eligibility,
treatment, market-share or uptake rate is applied, the cancer site may be wider than the
indication, and the price is before rebates. Each of these is written into the response's
`assumptions`, and what could not be computed into `missing`. For a very common condition the
product is far above any plausible sales and must not be read as one.

**Implementation (`scoring/rnpv.py`, `scoring/financials.py`, `GET /runs/{id}/financials`).** 10,000
draws (fixed seed: the same bundle gives the same range). PoS comes from Layer 3 phase by phase,
so a phase's cost is weighted by the probability of reaching it. Patients and analog price are the
P10/P50/P90 of the market estimate above, read as a triangle. The other inputs (peak share of
patients treated, rebates, contribution margin, years to peak, years of exclusivity, discount
rate, phase durations and costs) have **no source in the bundle: they are placeholders in
`RnpvConfig`, returned with every result as assumptions, and must be calibrated**. Sales stop when
exclusivity ends (no erosion tail). The tornado moves one input at a time between its low and
high end with the others at their base. Capital is the unweighted cost of the remaining phases;
time to milestone is the length of the current phase.

The stage is the one Open Targets gives the asset in the run's indication (Phase 1 to 3); only
when the bundle has none for that indication is it the asset's highest `maximumClinicalStage`
in any indication, and the assumption says which was used. An asset already approved in the
indication has no phase left and is not modeled. The therapy area is oncology when the
indication names a cancer, otherwise all diseases. If the stage cannot be read, or the market
cannot be sized, nothing is computed and the response says what is missing; the verdict then
has no rNPV and cannot be Invest. The same holds when the market size is a ceiling rather than
a market: an upper bound above $100 billion a year (`IMPLAUSIBLE_USD`, more than the largest
drug class earns) counts everyone with the condition, and a share of it is not a sales figure.

**K5 waits for calibration.** rNPV rests on the placeholder inputs above, and a kill criterion
needs a fact the evidence states. While `VerdictConfig.rnpv_calibrated` is false (the default),
a negative rNPV at P90 does not fire K5: it is recorded as the gate's `near_miss`, shown under
"What would change our mind", and the verdict stays at most Conditional because rNPV P50 is not
above zero. Set the flag only together with sourced inputs in `RnpvConfig`.

## Layer 5: Capital and time to next milestone

1. Effect size and SD from prior trials on the same endpoint.
2. Power calculation gives N patients.
   - Continuous endpoint, two arms: `n per arm = 2 * (z_(1-alpha/2) + z_(1-beta))^2 * sigma^2 / delta^2`
   - Time-to-event endpoint, 1:1 randomization (Schoenfeld): events `d = 4 * (z_(1-alpha/2) + z_(1-beta))^2 / (ln HR)^2`
   - Single-arm response endpoints use a stated design (for example a two-stage design); state it.
3. Cost = N x cost per patient for the therapeutic area + overhead (TODO benchmark source).
4. Duration from enrollment rate (registry analogs) plus follow-up.

Output: a range of capital and time to the next value inflection point (for example a Phase 2 readout). Report which assumptions dominate.

Implemented as `development_plan` (`scoring/rnpv.py`): from the stage alone, so a disease whose market
cannot be sized still has them. Three ranges (P10/P50/P90), all placeholders that say so in the
assumptions: capital to the next milestone (the cost of the current phase, up to its readout), time to
that milestone (the length of the current phase), and capital to approval (every remaining phase, not
risk-weighted). The first two describe the same milestone; the third is the whole road. The power
calculation above is not implemented: the phase costs are fixed defaults, not N x cost per patient.

## Module answers

The report is read as six modules: disease and unmet need, mechanism and biological validation,
preclinical to human translation, clinical development, competitive and commercial analysis,
investment underwriting. Each gives one answer, computed by code
(`scoring/module_answers.py`), so that a reader can follow answer -> claims -> quotes -> sources
and so that new evidence moves an answer only through the claims it touches.

Every claim carries an `implication`: what it means for an investor if it is true
(`favourable`, `unfavourable`, `neutral`). The model proposes it; code sets `neutral` on every
`unknown` and `unfavourable` on a claim that asserts a gate. A claim's pull on its module is

```
pull = sign(implication) x (2 x confidence - 1)
```

Confidence above 0.5 pulls the way the claim points. A favourable claim that contradicting
evidence takes below 0.5 pulls the other way: a refuted favourable claim counts against. Gaps,
hypotheses, neutral claims and claims whose quotes carry no weight pull nowhere.

`balance = (favourable - unfavourable) / (favourable + unfavourable)`, from -1 to +1. The answer:

| Condition, first that holds | Answer |
|---|---|
| A hard gate fired on a claim of the module | `against` |
| Total weight below 0.2 | `insufficient` |
| Balance <= -0.25 | `against` |
| Balance >= +0.25 and a soft gate fired on a claim of the module | `mixed` |
| Balance >= +0.25 | `supports` |
| Otherwise | `mixed` |

Sections map to modules as: `unmet_need`; `mechanism`; `translation`; `clinical` and `flags`;
`competition`, `commercial` and `ip_regulatory`. Investment underwriting has no claims of its
own: its answer is the verdict (`Invest` = supports, `Conditional` = mixed, `Do Not Invest` =
against), its claims are the key claims and the claims behind fired gates, and its headline
names the fired gates, PoS and rNPV.

**The verdict does not read these answers.** It follows from the gates and the investment model
below. The thresholds 0.2 and 0.25 are starting values that no eval run has calibrated; change
them only through the calibration protocol.

## Verdict mapping

Applied in order:

1. Any hard gate (K1-K5) fires: **Do Not Invest**.
2. Else any soft gate (S1-S6) fires: **Conditional**.
3. Else **Invest** if all hold: rNPV P50 > 0, translation-chain probability >= 0.5, key claims have confidence >= 0.7.
4. Else **Conditional**, listing the conditions.

All thresholds are config parameters set after running the eval set. LLMs lean optimistic and real biotech investors are sceptical, so most outputs should be Conditional or Do Not Invest; a verdict distribution that is mostly Invest is a calibration bug. Check by running all 20 drugs from the list.

## Top risks

At most three, each with the claim ids it rests on (`top_risk_claims`, see `data-model.md`): fired kill criteria first, then the claims that pull hardest *against* investing (the pull a claim has on its module answer, `scoring/pull.py`), one per independence group so one trial's result is not listed three times; the soft gates, unconfirmed kill criteria and key claims below the bar fill what is left. The Report links each risk to its claim and on to the quotation. A risk is never a model's sentence: it is a gate text or a claim of the report.

## What would change our mind

For each verdict, the report lists concrete conditions that flip it (for example "if Phase 2 response rate falls below X or discontinuation due to adverse events exceeds Y, the verdict becomes Do Not Invest"). These are generated from the gates and the tornado, not free text.

## Diligence questions

The Chair (a model step) proposes questions; each names one claim whose truth the answer would settle and the diligence that could answer it (proprietary data, patient-level data, KOL interview, experiment, CMC or IP diligence). Code adds a question for every `unknown` claim the Chair left out, and drops a question about a claim that is not in the report. Code then ranks them by value of information (`scoring/voi.py`), and the model never gives a value.

For one question the verdict is recomputed twice, with the claim settled as true (confidence 0.95, a stated fact, two independent sources) and as false (0.05). The value is the weighted sum of the two movements, the weights being the chance of each answer: the claim's confidence, or 0.5 for an `unknown` or `hypothesis` claim. A movement is the number of verdict steps (Invest, Conditional, Do Not Invest) plus half of the change in verdict confidence and in translation-chain probability, so a question that moves no verdict step still ranks by how much it moves the numbers. rNPV does not depend on the claims in this model (it follows from the stage and the market), so it is not part of the value.

A question whose answer cannot move the verdict alone, because another gap would hold the verdict where it is, is kept with a value of 0 and listed last: unanswered unknowns are never hidden. The values are relative and uncalibrated (the 0.95, 0.05 and 0.5 are placeholders like the other thresholds); read the order, not the number.

## Calibration protocol

1. Run the eval set (see `eval.md`) and plot the distribution of verdicts.
2. Compare verdicts and top risks with the recorded public-signal expectations.
3. Change thresholds or weights in config only with a logged reason.
4. Re-run the full eval after every change to prompts, weights or gates (regression test).
