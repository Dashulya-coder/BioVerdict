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
| K2 and K4 fire on keywords | `reasoning/gate_guards.py`, `stop_reason.py` | Partly done (#128): a lifted hold no longer supports K2; a business stop supports no K1, K2 or K4 (unit tests). Open: a registry record TERMINATED still supports K4 whatever the reason, and a boxed warning is not unmitigable toxicity |
| K1 did not fire for the pair | clinical module | The guard did not read "not superior to" or "endpoint was not met" as a failure (fixed in #128; K1 now fires for evobrutinib on its two phase 3 reports). Still open for the pair: whether a failed program of the class should kill a class question |
| An asset's registry search is not limited to the indication | `connectors/clinicaltrials.py` (`query.intr`) | Evobrutinib for MS (`R-34158eeca1b34375a86331eb442e5afc`) listed its rheumatoid-arthritis trials (ACR20) among the top risks |
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
6. **The gateway's concurrency limit is 3** (four probes on 2026-10-10; it was 4 from one
   observation) and is enforced inside one process (`llm/providers/openai.py`). Two runs started
   through the API at once exceed it.
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

## To Arsenii, from Dasha — 2026-10-10 (updated after stage 1)

Your consent was waived for the finals, so I did the collection for multiple sclerosis myself,
in the area of your connectors (`connectors/openfda.py`, `connectors/ema.py`,
`connectors/pubmed.py`, `pipeline/live_sources.py`). Please read it when you have time; what
changed is in [`collection.md`](collection.md) ("Three tools were added for the finals").

### Done

- Drugs approved for the indication (Open Targets names them, openFDA gives the brand labels),
  the EU register (EMA open data, so EMA is in: the catalog is whatever the connectors fetch,
  there is no separate list) and class safety from PubMed with reviews allowed (all reviews one
  source). New source family `approved_for_indication`.
- The competition module read only `registry` and `target_database`: no FDA label ever reached
  it. It reads the new family now, as do unmet need and commercial.

### Still open, and it is yours to say

- The FDA complete response letter for tolebrutinib (Sanofi, 2025-12-24) has no source.
- Oncology analogs by target are still up to 8 per target; they crowd the commercial section.
- Why 6 of the 11 registry trials of the pair stay uncited: I check the reasoning side.
- Balance calibration: the two thresholds (0.2 and 0.25 in `scoring/module_answers.py`), and
  whether to count by trial or by claim. I would decide after a live run on the new collection.
- Approval of `Claim.implication` (decision 1 above), which entered the shared contract without
  the two-step approval.

---

## To Dasha, from Arsenii — 2026-10-11

**The interface was redesigned and merged** (#132, #133), and it touches your folders
(`features/report/`, `features/trace/`). The palette is a neutral black; colour goes on marks
(a bar, a ring, a border, the square of a badge) and not on words, so the verdict is written in
plain ink with a coloured ring beside it. The Report opens with an overview on one screen
(`Overview.tsx`), and "Six modules, six answers" shows one module at a time, its claims in two
columns, against and for. Compare opens with both verdicts side by side and gives each module a
track for its balance before and after. Texts and API shapes are unchanged, except that one
browser test now picks a module before it reads it. The rules are in
[`design-system.md`](design-system.md), the stage order in [`demo-script.md`](demo-script.md),
the screens on the [Canva board](https://www.canva.com/d/RAqo-unHbPofeXK) (pages 2 to 8 are the
merged state; the later pages are earlier options).

**Please look, on your latest run:** the Report with a written case ("The underwriting case"
was seen empty only, the stored run here has none), and Compare on a real recompute with six
modules and several causes (seen on test data only). Say if a block reads wrong.

**From reading #111 to #128** (no paid run; `pytest`, ruff, `check_compat` and the frontend
checks pass on `main`):

- `api/report.py:_judged_states` takes the evidence id from the first word of a check's
  `detail`. It works with today's two texts in `verification/entailment.py`; a change of either
  text silently turns every link into "not judged". A field for the evidence id on
  `VerificationCheck` would remove the coupling (shared model: both approve).
- `verification/entailment.py` imports `result_lines` from `connectors/clinicaltrials.py`:
  verification now depends on a connector. The formatter could live beside the store models.
- `reasoning/synthesis.py` checks digits only: "three trials" or "half of the patients" passes
  as a sentence without a number.
- In a `classify` recompute a gap is retired as soon as a new claim names its chain link. If
  the judge then removes that claim's only quote, the link is held by a hypothesis and the
  `unknown` claim is gone. Decide whether the gap should come back in that case.
- A run now costs about $3.10 and takes about 9 minutes (`cost.md`), against $0.99 and 5 minutes
  before #125; `RUN_BUDGET_USD` is 5. Two attempts on stage are close to the limit of one run
  each: record the demo runs beforehand.


---

## To Arsenii, from Dasha — 2026-10-11

Your #132 and #133, checked on real runs (BTK x MS, and the evobrutinib comparison of the case
with its control) at 1440 and 390 px; fixed on `dasha/B5-overview-follows-the-rule`:

- **The note under the verdict** (`Overview.tsx`) now says what the rule says: Do Not Invest only
  from a kill criterion on a claim confirmed by independent sources; Conditional is a soft gate,
  an unconfirmed kill criterion or an unmet Invest condition, not "promising".
- **The translation chain tile** stands one link under the other below `sm`: at 390 px the five
  names ran into each other.
- **"From sources to verdict" in a recompute** says "new quotes read by the judge in this
  recompute": the judge reads only the added evidence there, so the evobrutinib case showed "2".
- **Compare on a phone** (`DiffView.tsx`, your folder): the two verdicts overlapped and the table's
  After column was cut; the sides now stack below `sm` and long values wrap.

The Compare screen on the real comparison reads well: verdict before and after, K1 fired, the
two quotes on C-0089 with its confidence and pull. The open item of your #133 test plan is done.
