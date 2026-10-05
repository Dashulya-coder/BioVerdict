# Domain pack: precision oncology (RAS/KRAS and WRN)

The core system is domain-agnostic. This pack adds domain knowledge as checklists and configuration, not as prompt text hard-coded in the core. Universality is tested separately on a second domain (see `eval.md`).

## Why this domain

- Public data is rich and structured (registry IDs, papers, SEC exhibits, press releases).
- The assets span maturity from late-stage to first-in-human, which gives a natural depth gradient for the leakage test.
- The biomarker (mutation or MSI-H) defines the population, endpoint and trial design.
- Real dated events exist for the time-travel demo (see `demo-script.md`).

## Assets (verify status before use)

| Asset | Mechanism (per the organizers' list) | Notes found during research (verify in primary sources) |
|---|---|---|
| Divarasib | next-generation KRAS G12C inhibitor, NSCLC | Phase 3 Krascendo 1 (NCT06497556) vs sotorasib or adagrasib; Roche release 2026-07-02; breakthrough designation 2022, orphan designation 2026; Krascendo 3 (NCT07541170) adjuvant |
| Elironrasib (RMC-6291) | KRAS G12C(ON) tri-complex inhibitor | Developer's filings mention a registrational strategy update planned for 2026 |
| Zoldonrasib (RMC-9805) | KRAS G12D(ON) tri-complex inhibitor | Breakthrough designation 2026-01; first Phase 3 started in first-line PDAC |
| HRO761 | WRN helicase inhibitor, MSI-high solid tumors | Phase 1/1b NCT05838768; discovery paper in Nature (2024); independent report of resistance mutations; competitor RO7589831 (VVD-214) Phase 1 |

**Alias warning.** A source used a similar-looking name ("elisrasib") for a G12C inhibitor. We did not confirm whether it is the same molecule as elironrasib. The Resolver must disambiguate by ChEMBL/registry ID, never by string similarity.

## Endpoints and conventions

| Endpoint | Notes |
|---|---|
| ORR | RECIST 1.1; confirmed vs unconfirmed must be stated |
| DCR | includes stable disease; weaker evidence than ORR |
| PFS | blinded independent central review (BICR) preferred; primary in many randomized trials |
| OS | key secondary or primary; crossover affects interpretation |
| DoR | duration of response |
| ctDNA clearance | exploratory biomarker; record, do not over-weight |

Trial design checks: single-arm vs randomized; comparator (standard of care or an approved class member); line of therapy; biomarker selection; sample size; follow-up.

## Population and epidemiology

- Biomarker-defined subsets (for example a KRAS variant within NSCLC, or MSI-H within colorectal, endometrial and other tumors).
- Use SEER, GCO and CDC for incidence, and published prevalence of the variant for the biomarker fraction. Combine in code (`derived`), never from LLM memory.

## Analog classes (reference class inputs)

- First-generation KRAS G12C inhibitors and their approved comparators.
- RAS(ON) tri-complex inhibitors.
- Other synthetic-lethality targets in oncology.
- WRN inhibitors in clinical testing.
- For MSI-H tumors, the immune checkpoint inhibitor context (standard of care in part of the population).

## Checklist prompts (questions to ask, not claims)

- Is there on-target or class toxicity in human data? What dose reductions or discontinuations occurred?
- Is resistance reported, and by what mechanism (preclinical vs clinical)?
- Is target engagement in tumor tissue shown, or only inferred from response?
- Is the benefit specific to the biomarker-selected population?
- What would the next randomized trial need (comparator, endpoint, N)?
- Is the effect durable in patients who progressed on the previous standard?

## Probability-of-success inputs

- Oncology has below-average approval likelihood in the BIO/Informa/QLS benchmarks; programs with patient preselection biomarkers show higher likelihood. Use the primary report for exact figures (`sources.md`).
- Somatic genetic evidence in oncology is also associated with higher success (Minikel et al., 2024); verify the value for oncology in the paper.

## Red-flag patterns to look for

- Press release says "on track" while the registry shows a changed status.
- Response rate reported without confirmation status.
- Different comparators across trials presented as head-to-head.
- Resistance mechanisms reported for the asset or its class.
- Small expansion cohorts used to support broad claims.
