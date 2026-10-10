# Hand-over notes

Open notes from one track to the other. A coding agent that starts work in this repository
reads this file (see `AGENTS.md`) and tells its user what is addressed to them before it
starts on anything else. Delete a note when it is done; delete the file's last note and leave
the heading.

---

## To Dasha, from Arsenii — 2026-10-10

State of `main`: through #107. What changed today is in #105 (six module answers, per-module
diff, fixes from the first live runs, sensitivity benchmark) and #107 (recompute and registry
fixes, asset selection, `docs/finals-audit.md`). The finals rubric and the stage order are in
[`demo-script.md`](demo-script.md).

**Arsenii made three paid runs and will make no more.** The paid runs below are yours.

### 1. Do first: paid runs before the demo

1. **(Done 2026-10-10, Dasha: Conditional, 357 s, $0.99; `docs/eval.md` section 9.) A live run of the pair on merged `main`.** From `backend/`:
   `USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --query "BTK inhibitor for multiple sclerosis"`.
   The unmet-need prompt, the last judge changes and everything in #107 were made after the
   last live run and have been seen only in tests.
2. **(Done 2026-10-10, Dasha: 3 of 5 passed; `docs/eval.md` section 9.) A base run with an earlier cutoff, then the sensitivity benchmark.** Add `--as-of 2024-06-30`
   to the command above, then
   `uv run --env-file ../.env bioverdict sensitivity --run <run id> --cases ../eval/sensitivity.yaml --out ../eval/results/<date>`.
   The benchmark has never been run with a real model. Put its table in
   [`eval.md`](eval.md), section 9. A case that fails is shown as failed.
3. **Before that base run, know this:** since #107 registry results are dated by the record's
   last update, not by their first posting. A run as of 2024 will see fewer trial results than
   before, possibly too few to stand on. If so, choose a later cutoff and move the `as_of` of
   the cases with it.
4. **Raise `RUN_TIMEOUT_S` on the demo machine** and pre-warm the model cache. The three runs
   took 3 min 45 s, 7 min 21 s and 5 min 7 s against a limit of 420 s; the second lost its Chair
   step to the limit.
   (Partly done 2026-10-10, Dasha: `.env` on her machine says 900 and `doctor` is green; the
   demo machine is still to check.)
5. **(Done 2026-10-10, Dasha: Report, Compare and Trace on run `R-20261010-125211-cf5016`;
   three defects found, fixed in #112 except "top risks".) Look at the Report and Compare
   screens on a live run.** "Six modules, six answers" and "Module by module" had been seen
   only in browser tests.

Measured on the last run (R-440107f1…, 2026-10-10): $0.99, Conditional, 100 claims, 72
citations judged and 13 removed, 37 links of context claims not judged, 8 diligence questions.

### 2. To finish in your track

| What | Where | Why it matters |
|---|---|---|
| The judge keeps a link it did not answer for | `verification/entailment.py`, `pipeline/reason_score.py:verify_pass` | A failed request or a skipped item leaves the quote counted as support. Either show an explicit "not verified" state, or keep such claims from deciding a module's answer and the verdict |
| Nobody has read the 13 removals | a hand-labelled sample of about 30 claims (`eval.md`, "Judge agreement") | The judge went from removing 75 of 93 to 13 of 72 after it was shown the passage; whether it is now too lenient is unknown |
| Unmet-need module reported the class's own trial failures and answered "against" | `reasoning/modules.py`, `_UNMET_NEED` | Prompt changed, not seen live |
| Modules restate one another | mechanism, translation and clinical prompts | One trial result is written by three modules and pulls on each |
| K2 and K4 fire on keywords | `reasoning/gate_guards.py`, `stop_reason.py` | A terminated study is not a stopped program; a boxed warning is not unmitigable toxicity. Add negative controls: a business stop, a lifted hold |
| K1 did not fire for the pair | clinical module | The registry record of evobrutinib says the primary endpoint was not met. Decide whether silence is right for a class question or the model missed it |
| `eval/cases.yaml` has one smoke case | B10 | No regression set |

### 3. Decisions to think over together

Each of these was made by one person under time pressure, or not made at all.

1. **`Claim.implication` entered the shared contract without the two-step approval** of
   `CONTRIBUTING.md` (#105, migration 4). A model proposes it and the module answers depend on
   it. Accept it, or have code set the label by rule?
2. **A module's answer is a balance with two uncalibrated thresholds** (0.2 and 0.25,
   `scoring/module_answers.py`). Splitting one finding into several claims moves the balance.
   Count by trial or by independence group instead of by claim?
3. **Class question or asset.** For an indication with a mechanism and no drug, PoS is taken
   from the most advanced program of the class, stated as an assumption (Arsenii's decision;
   the second audit proposed no PoS until an asset is chosen). Choosing an asset is in the UI,
   but it is a second whole run. Is a cheaper path worth building: reuse the class bundle for
   the asset?
4. **The judge does not read context claims** (neutral, not key, no gate, no chain link), to
   fit the time limit. Does that agree with "a claim that fails verification is dropped"?
5. **The judge is a model of the same vendor** as the model that writes the claims: the
   gateway lists no other. An independent check needs a second adapter and key.
6. **The gateway's concurrency limit (4) comes from one observation** and is enforced inside
   one process (`llm/providers/openai.py`). Two runs started through the API at once exceed it.
7. **Incremental recompute and a gap.** A new fact that shows a translation-chain link is now a
   translation claim with its `chain_link`, and it retires the `unknown` claim of that link
   (tested with fakes, not yet with a real model). Evidence the model links *to* the `unknown`
   claim itself still leaves its confidence at the default: the prompt asks for a new claim
   instead. Decide whether code should also refuse such a link.
8. **rNPV.** There is none for multiple sclerosis (no prevalence source). Where there is one it
   rests on placeholders, and the rule is asymmetric: a negative rNPV does not kill, a positive
   one helps reach `Invest`. Remove the asymmetry, or say it on stage.
9. **Analogs are chosen by target.** For multiple sclerosis the commercial module reads
   oncology BTK labels and prices, and the real competitors in the indication are absent.

The findings behind these, numbered, are in [`finals-audit.md`](finals-audit.md) (read its
status note first); the ordered list of what is open before the demo is in
[`work-plan.md`](work-plan.md).

---

## To Arsenii, from Dasha — 2026-10-10

I read the report of a second live run of the pair (`R-20261010-125211-cf5016`, Conditional,
$0.87, 156 evidence items) against the finals rubric. The plan that follows from it is in
[`work-plan.md`](work-plan.md), "Final plan". Your part is stage 1: collection for multiple
sclerosis. It is the longest path, because every paid run I make for the benchmark has to come
after it. If it cannot be ready, the reference documents go in through add-evidence on stage.

### 1. Competitors by indication, not analogs by target

- No claim of the run names an approved MS drug. I searched all claims for ocrelizumab,
  ofatumumab, siponimod, fingolimod, ozanimod, natalizumab, interferon and glatiramer: 0 hits.
  Teriflunomide appears only as the comparator of BTK trials.
- The competition section holds 12 claims that restate the trial results of tolebrutinib and
  evobrutinib (the clinical module's). The FDA labels sit in the commercial section: Imbruvica,
  Calquence (lymphoma, CLL), Litfulo (alopecia), Wayrilz (thrombocytopenia). Eight of its 18
  claims say the same thing ("taken orally").
- Wanted: approved drugs for the indication (FDA labels whose indications name multiple
  sclerosis; trials of the indication in the registry), and fewer analogs by target. Analogs
  are 45 of the 156 evidence items, and 13 of those 45 are cited by a claim.

### 2. Regulatory status and class safety

- Nothing on liver injury reached the bundle or any claim: it is the best known risk of the
  class. The EU authorised tolebrutinib as Cenrifki on 2026-06-19 (adults with secondary
  progressive MS without relapses in the last two years, liver monitoring; EMA page, checked
  2026-10-10). The FDA issued a complete response letter for non-relapsing secondary
  progressive MS (Sanofi, 2025-12-24). Neither is in the run.
- The EPAR is not on the source catalog allowlist. **Your decision:** add EMA, or find these
  facts in a source that is already allowed.
- The fenebrutinib filing acceptance and FENtrepid (Roche) are also absent; both are in the
  reference set of `finals-audit.md`.

### 3. Evidence that is in the bundle and used by nothing

- 117 of 156 evidence items are cited by no claim. Six of the 11 registry trials have no
  citing claim: NCT04458051 (PERSEUS), NCT04742400, NCT05064436, NCT07067463, NCT07299019,
  NCT07776743. I do not yet know whether the reasoning modules are given these records or a
  limit cuts them. I check that on the reasoning side; you need not.

### 4. For your review

- #112: an additive field `ClaimView.checks` (the checks a claim failed: why a quote was
  removed). It also touches `features/compare/CompareRuns.tsx`, your folder (a subtitle that
  read "report of :" for a run without a drug).
- To come: an additive API field that marks links of context claims as not judged.
- To come: a proposal to change the shared `VerdictResult.top_risks` (now `list[str]`, at most
  three) so that each risk carries its claim ids. By `CONTRIBUTING.md` it is a PR in
  `data-model.md` first, and both approve before code.
- To come: a PR in your areas A7 and A8: a `classify` recompute that attaches a new claim to a
  chain link, and a sensitivity runner that compares each case with a control recompute at the
  same cutoff.

### 5. Open between us

- Balance calibration: the two thresholds (0.2 and 0.25 in `scoring/module_answers.py`), and
  whether to count by trial or by claim. Unmet need sits at weight 0.21 against a floor of
  0.20 on one claim; mechanism at balance 0.254 against 0.25. I would decide after the new
  collection, not before.
- Adding EMA to the catalog (section 2).
- Approval of `Claim.implication` (decision 1 above), which entered the shared contract
  without the two-step approval.
