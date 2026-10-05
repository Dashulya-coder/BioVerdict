# Final demo script

Goal: show `Indication + Mechanism -> Evidence -> Underwriting -> Recommendation`, and at least one case where new or contradictory evidence changes the conclusion, as an architectural property that judges can test themselves.

Total target: TODO minutes (confirm with organizers).

## Preparation

- [ ] Cache pre-warmed for every demo asset (retrieval and LLM responses). One live-capable path works as a fallback.
- [ ] Model and effort fixed, `temperature` fixed, versions logged.
- [ ] Recorded runs stored with their bundle hashes.
- [ ] Trace panel shows tokens and cost.
- [ ] Verify every date, number and URL below against the primary source on the day.

## Flow

1. **Input (30 s).** Enter an indication + mechanism, then a drug name, then a company code. The Resolver shows IDs and its `assumptions`.
2. **Report (60 s).** Executive verdict first: verdict, confidence, top 3 risks, capital and time range, "What would change our mind".
3. **Drill-down (60 s).** Verdict -> claim -> evidence quote -> source link. Show a badge for the claim's basis. Show one claim that the verifier dropped, and why.
4. **Honesty on a sparse asset (60 s).** Run a very sparse asset. Show `evidence sparse`, a wider range, statuses (`not_reported`, `none_found`), and ranked diligence questions with the type of data needed.
5. **Change of conclusion A: time-travel (90 s).** Same asset with `as_of` before and after a real event. Show the diff screen.
6. **Change of conclusion B: add evidence live (90 s).** Paste a document from the judges, or use a prepared one. Show a weak result lowering confidence only, then a strong result flipping the verdict.
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
- The same input twice gives the same verdict and the same top risks.
- A new document produces a diff with named causes.

## Fallbacks

| Problem | Action |
|---|---|
| Network fails | Run from cache; say so |
| Provider rate limit | Failover is automatic; trace shows `mixed_models` |
| Run too slow | Use a recorded run and explain the live path |
| Judge supplies an unfamiliar format | Resolver shows `assumptions`; continue |

## Q&A answers to prepare

- How did you avoid leakage? (closed-world bundle, quote gate, leakage probe, Obscure vs Emerging comparison)
- Where does each number come from? (extracted with source, derived by code, or modeled with visible assumptions)
- What does the system not know? (see `limitations.md`)
- How did you calibrate the verdict? (eval set, distribution, logged changes)
