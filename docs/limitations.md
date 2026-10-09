# Limitations: what the system cannot know

Being clear about this is a feature. The system is designed to say "we do not know, and here is how to find out".

## What cannot be answered from public information

| Question | Needs |
|---|---|
| Is the efficacious human exposure achievable safely? | proprietary PK/PD and safety data |
| Is target engagement shown in the relevant tissue? | proprietary experiments or biopsies, patient-level data |
| Why did the closest prior program fail? | company disclosure, KOL interviews |
| Does the biomarker predict clinical benefit? | patient-level clinical data |
| Is the observed biology target-specific? | additional experiments (for example orthogonal perturbation) |
| What evidence would kill the program? | expert judgment and design of the next trial |
| Freedom to operate, patent scope for unapproved assets | IP diligence |
| Manufacturing, COGS, supply risk | CMC diligence |
| Pricing and uptake for a new class | payer interviews, market research |

These become diligence questions with the data type named.

## Structural limits

- **Public data only.** Curated commercial databases are out of scope.
- **Unapproved drugs:** no label, no adverse-event database, no Orange/Purple Book entry; see `sources.md`.
- **Language models guess.** The closed-world design and quote gate reduce, but do not eliminate, wrong or unsupported claims. The entailment judge is scored against a manual sample and is not perfect.
- **Historical backtests leak.** Models know many outcomes; we judge arguments and risks, not only verdicts.
- **No ground truth.** Outcomes take years; we measure process quality, stability and sensitivity.
- **Calibration is limited.** Thresholds are tuned on a small set built from public signals, not on expert verdicts.
- **Priors are coarse.** Base rates are class-level benchmarks; asset-specific adjustments are modeled and uncertain.
- **Coverage varies by asset.** Companies disclose different amounts; sparse assets get wider ranges, never filled gaps.
- **Free tiers and rate limits** constrain throughput and may constrain data handling; our inputs are public.
- **A registry has no history here.** ClinicalTrials.gov serves the current text of a record. Every part of it (summary, endpoints, status, design) is dated by the record's last update, so a run replayed at an earlier date does not see that study at all rather than seeing wording that may have been written later. Posted results are dated by their own posting date.
- **A positive verdict is not reachable yet.** `Invest` needs a positive rNPV from the investment model, which is not built (B7); until then the best verdict a run can give is `Conditional`, and the report says which condition is missing.
- **A model call that timed out keeps running in its thread** until the provider answers; its late answer is discarded.

## Out of scope

- Trading or portfolio advice.
- Regulatory submissions or legal opinions.
- Non-public data.

## Responsible use

Outputs are a structured starting point for human diligence, not investment advice. Every number is traceable to a source or labelled as a model assumption.
