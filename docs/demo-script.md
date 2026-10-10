# Final demo script

The finals score six modules, 15 points each, plus 10 for UI and usability:

| Criterion | What the judges must see | Where it is on screen |
|---|---|---|
| A. Conflicting evidence (5) | the module changes its answer on new or contradictory data, and names the evidence that caused it | **Compare**: the verdict before and after side by side, then "Module by module": each module's answer before and after, its balance on an against/for track (ring before, dot after), and under it the quote, the claim it was placed on and what it did to that claim |
| B. Evidence flow (5) | Recommendation -> Claims -> Evidence -> Sources | **Report**: the overview names the verdict and the six answers on one screen; click a module there, or pick it in "Six modules, six answers": its claims stand in two columns, "Pulls against" and "Pulls for"; open a claim, read the verbatim quote, follow the source link |
| C. Quality (5) | what the system produces for the announced pair, and how it was benchmarked | the live report for the pair; the sensitivity benchmark table with its method and named items ([eval](eval.md), section 8) |

The pair for every team: **BTK inhibitor x multiple sclerosis**. The presentation and the answers
are in English.

## The six modules and where each gets its points

Every module has the same three moves; rehearse them per module, about 40 seconds each.

| Module | B: open this | A: the change to show | C: what to say about quality |
|---|---|---|---|
| Disease and unmet need | its module: answer, then a claim from a treatment guideline with its quote | time-travel diff: the module before and after the later publications | what the guidelines in the bundle say; what is an honest `unknown` |
| Mechanism and biological validation | its module: the Open Targets association and the trial results cited as pharmacological evidence; the genetics gap as `unknown` | sensitivity case `weak-microglia-preprint`: the balance moves a little, the answer holds | laboratory evidence weighs little by rule (level weights), not by a model's mood |
| Preclinical to human translation | the chain: five links, each `supported`, `weak` or `missing`, with claims | sensitivity case `strong-fenebrutinib-lesions`: fewer new MRI lesions is the biological-response link, which goes from weak to supported | a missing link is a finding and caps the verdict (gate S1) |
| Clinical development | its module: trial results with NCT ids and posted numbers | sensitivity cases `strong-tolebrutinib-not-superior` and `strong-evobrutinib-not-superior`: two failed phase 3 trials, each naming its PMID | results are quoted from the registry and PubMed, never from memory |
| Competitive and commercial | its module: class competitors by phase, approved analogs and their labels | time-travel diff, or a new competitor record added | market size is code's, from sources; for MS it is reported as missing, not guessed |
| Investment underwriting | its module: the verdict, the gates that fired with their claims, PoS with its benchmark source | Compare: verdict and gates before and after, and the evidence on the key claims | the verdict is a rule over gates and numbers; say which condition holds it at Conditional |

Then the noise case (`noise-kras-lung-release`): a document about another disease moves nothing.
That is the third thing criterion A asks for implicitly: change for the right reason only.

## Order on stage (target about 7 minutes; confirm with organizers)

1. **Input (20 s).** Type `multiple sclerosis` and `BTK inhibitor`. Show the resolved target, and
   the assumption the Resolver states about how Open Targets files the disease.
   The resolved-input screen also lists the drugs found in experimental arms of the registry
   records ("Choose an existing asset"): choosing one prepares an asset-specific run.
2. **Report, the overview (90 s).** One screen: the verdict with its confidence ring, the six
   modules on one against/for axis, the modeled figures, the translation chain, the gates, and
   "From sources to verdict" (records, claims, quotes the judge read, quotes it kept). Read the
   six answers aloud once. Say what is not computed for this pair (rNPV, capital, time) and why.
3. **Evidence flow (90 s).** Click two modules of the judges' choice in the overview. Each opens
   with its scale and two columns, "Pulls against" and "Pulls for"; open one claim on each side
   down to its quote and its source. Say: the answer is computed by code from these claims, and
   the number above a claim is its pull.
4. **Conflicting evidence, time travel (60 s).** Compare the run with the earlier-cutoff run.
   The top shows both verdicts side by side. Read "Module by module": a moved module has a bar
   on its left and its track shows where the balance stood and where it stands; an unchanged
   one says so. Read the evidence under a moved module.
5. **Conflicting evidence, live (90 s).** Paste one strong sentence from `eval/sensitivity.yaml`
   (or a judge's document) into Compare. Show the module that moved, the quote and the claim.
   Then the noise document: nothing moves.
5a. **The verdict changes (60 s).** Evobrutinib before its phase 3 read out (as of 2023-11-30) is
   Conditional. Add the two documents of `eval/sensitivity-evobrutinib.yaml`
   (`strong-evolution-phase3-failed`): the verdict becomes Do Not Invest, gate K1 fires on one
   claim that cites both, and Compare names them. Then the FDA's partial hold alone: one source,
   the verdict stays Conditional. Recorded runs: control `R-653fa48f3b214b8383c66c3faa0fd1b1`,
   case run in `eval/results/2026-10-10-evobrutinib-3/sensitivity.json`.
6. **Benchmark (40 s).** The sensitivity table: method in two sentences, the five named items,
   pass or fail for each. Say all of it: 5 of 5 on 2026-10-11, each case against a control at
   the same cutoff; 3 of 5 before, and the fenebrutinib case passes under an expectation that
   was changed, with its reason (`eval.md`, section 9); the cases were used to find defects, so
   this is a development set, not a held-out score.
7. **Trace and cost (20 s).** Time, cost, models, what code dropped.

## What is not ready (2026-10-11): do before the demo

- [x] Live runs of the pair on the current code (`eval.md`, section 9) and a base as of
      2024-06-30 with the sensitivity benchmark (3 of 5, on an earlier version).
- [x] **A case where the verdict itself changes**: evobrutinib, Conditional → Do Not Invest on
      the two reports of its failed phase 3, with a one-source control (step 5a; `eval.md`,
      section 9). The lifted-hold and business-stop controls are unit tests (no verified public
      text of a lifted hold was found).
- [x] The BTK x MS benchmark (`eval/sensitivity.yaml`) re-run with its control on the current
      code: 5 of 5 on 2026-10-11 (`eval.md`, section 9).
- [ ] **Two modules have no controlled case for criterion A**: disease and unmet need, and
      competitive and commercial. `eval/sensitivity.yaml` moves clinical development (two
      cases), translation and mechanism; the verdict case covers investment. For the other two
      the script has only the time-travel diff. Candidates named in `work-plan.md`: PERSEUS for
      unmet need; FENtrepid or the acceptance of the fenebrutinib filing for competition. Each
      needs a verbatim quote checked against its source, and a paid run.
- [ ] **Look at the new Report and Compare screens on a run that has a written case** and at
      phone width: both were checked on a stored run without one, and in browser tests.
- [ ] **Liver safety.** The run checked for coverage had no evidence and no claim on liver
      injury, the best-known risk of the class. Class safety has been collected from PubMed
      since (`collection.md`); the coverage table of `eval.md` was not taken again. Check a fresh
      run before saying anything about safety on stage.
- [ ] **Other pairs.** The organizers said the judges may enter queries whose answers their
      specialists already have. The system has been run with a real model on this pair only (and
      on evobrutinib). Run two or three other pairs beforehand and warm the cache: a first run
      takes about 9 minutes.
- [ ] Record the demo runs on the frozen code and keep their bundle hashes: a run now takes about
      9 minutes, too long for the stage.
- [ ] `RUN_TIMEOUT_S`: a run for this pair took 4 to 7 minutes on the gateway with four module
      batches; with up to eight (all of the bundle read) expect about ten. The old default of 420
      seconds cut the Chair off once; the default is now 1500. A `.env` copied from an older
      `.env.example` says 420 or 900: set it to 1500 on the demo machine, and pre-warm the model cache.
- [ ] rNPV for multiple sclerosis is not computed (no open prevalence source in the connectors).
      Say so; do not present a market number.

## Who presents what

| Part | Presenter |
|---|---|
| 1 Input and resolver, sources and evidence, add-evidence and diff (steps 1, 3, 5, 6) | Arsenii |
| 2 Executive verdict, translation chain, verdict logic, sparse asset honesty (steps 2, 4) | Dasha |
| 7 Trace and cost; Q&A | both |

Swap if it fits better; rehearse the hand-overs.

## Preparation

- [ ] Cache pre-warmed for every demo asset (retrieval and LLM responses). One live-capable path works as a fallback.
- [ ] Model and effort fixed, `temperature` fixed, versions logged.
- [ ] Recorded runs stored with their bundle hashes.
- [ ] Trace panel shows tokens and cost.
- [ ] Verify every date, number and URL below against the primary source on the day.

## Earlier flow (oncology assets; kept for the candidate events below)

1. **Input (30 s).** Enter an indication + mechanism, then a drug name, then a company code. The Resolver shows IDs and its `assumptions`.
2. **Report (60 s).** Executive verdict first: verdict, confidence, top 3 risks, capital and time range, "What would change our mind".
3. **Drill-down (60 s).** Verdict -> claim -> evidence quote -> source link. Show a badge for the claim's basis. Show one claim that the verifier dropped, and why.
4. **Honesty on a sparse asset (60 s).** Run a very sparse asset. Show `evidence sparse`, a wider range, statuses (`not_reported`, `none_found`), and ranked diligence questions with the type of data needed.
5. **Change of conclusion A: time-travel (90 s).** Same asset with `as_of` before and after a real event. Show the diff screen.
6. **Change of conclusion B: add evidence live (90 s).** Paste a document from the judges, or use a prepared one. Show a weak result lowering confidence only, then a strong result moving a module's answer. The verdict changes only if the document fires a gate; no benchmark case shows that yet.
7. **Trace and cost (30 s).** Run time, tokens, cost, models used, failover count.

## Candidate events (verify before use)

### A. Divarasib, time-travel

- Run with `as_of = 2026-06-30` and with the current date.
- Event between them: Phase 3 Krascendo 1 (NCT06497556), a randomized comparison of divarasib with sotorasib or adagrasib in previously treated KRAS G12C NSCLC. Roche announced positive results on 2026-07-02 (progression-free and overall survival superiority vs approved class members).
- Source: https://www.roche.com/media/releases/med-cor-2026-07-02
- Expected diff: new Phase 3 evidence, changed competitive-position claims, higher confidence on efficacy claims, updated PoS and rNPV. Do **not** pre-write the final verdict; show what the system outputs.
- Risk: models released after July 2026 may know the result. The closed-world gate should drop unsupported claims; report the count.

### B. HRO761, contradictory evidence and a missing translation link

- Phase 1/1b NCT05838768; interim analysis reported in Annals of Oncology (ESMO abstract 925MO): https://www.annalsofoncology.org/article/S0923-7534(25)02414-7/fulltext
- Discovery and preclinical pharmacology, Nature 2024: https://www.nature.com/articles/s41586-024-07350-y
- Resistance mutations reported against HRO761 in cells and in vivo: https://pmc.ncbi.nlm.nih.gov/articles/PMC13434289/ (check whether this is a preprint)
- Competitor RO7589831 (VVD-214) Phase 1, Nature Medicine; authors note direct pharmacological inhibition in the tumor is still pending confirmation: https://www.nature.com/articles/s41591-026-04657-3
- Demonstrates: a translation-chain link shown as `weak` or `missing`, contradicting evidence, and honest diligence questions.

### C. Zoldonrasib, designation and late-stage start

- Breakthrough Therapy designation in 2026-01 and a first Phase 3 start in first-line pancreatic cancer. Sources: developer's 8-K exhibits on https://www.sec.gov and press coverage.

### D. Strong vs weak counter-evidence (controlled)

- **Weak:** a single in vitro or preclinical report. Expected: confidence of a human-evidence claim drops slightly, verdict unchanged.
- **Strong:** a clinical hold, termination or a clearly negative human readout. If no real event exists for the chosen asset, use a **clearly labelled synthetic document** and say so on screen.
- **Noise:** an unrelated document. Expected: no material change.

## What judges can verify themselves

- Every claim opens its quote and source.
- The same bundle gives the same verdict: scoring is code. Repeated runs with a real model were not measured (`eval.md`, "Not done"); on this pair the verdict was Conditional in every run, while one module's answer differed between runs.
- A new document produces a diff with named causes.

## Fallbacks

| Problem | Action |
|---|---|
| Network fails | Run from cache; say so |
| Provider rate limit | Failover is automatic; trace shows `mixed_models` |
| Run too slow | Use a recorded run and explain the live path |
| Judge supplies an unfamiliar format | Resolver shows `assumptions`; continue |

## Q&A answers to prepare

- How did you avoid leakage? (closed-world bundle with an evidence cutoff; a claim stands only on a verbatim quote from a dated record; code computes the verdict. Say also what was not done: the closed-book probe and the comparison with a model that has no retrieval were not run, and the backtests were not run on the current code)
- Where does each number come from? (extracted with source, derived by code, or modeled with visible assumptions)
- What does the system not know? (see `limitations.md`)
- How did you calibrate the verdict? (eval set, distribution, logged changes)
