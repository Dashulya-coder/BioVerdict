# Data sources and attribution

Rule: evidence comes only from sources listed here and only through connectors. Each evidence item records the source, URL, locator and retrieval time. Source evidence and AI inference are always distinguished (see `data-model.md`).

## Source-family order and conflict rules

Inspired by the closed-world approach described by Unobio in "Workflow, Not Agent" (https://unobio.com/blog/workflow-not-agent-deep-research-an-analyst-can-trust).

When two sources disagree:

1. **Family order** (default): regulatory label, then posted ClinicalTrials.gov results, then SEC filings, then peer-reviewed papers, then company press releases and presentations.
2. **Match first, then date.** Two numbers compete only if they measure the same endpoint in the same population. If they do, the later data cutoff wins.
3. **Unresolved stays unresolved.** If both survive, show both and mark the section `conflicting`.
4. A gap between a press release ("on track") and the registry status ("terminated") is itself a red flag.

## Connectors

| Domain | Source | Access | Used for |
|---|---|---|---|
| Trials | ClinicalTrials.gov v2 API | https://clinicaltrials.gov | Phase, sponsor, enrollment, endpoints, status, posted results |
| Trials | AACT (optional) | https://aact.ctti-clinicaltrials.org | `why_stopped`, aggregates; only if time allows |
| Targets and drugs | Open Targets (GraphQL) | https://platform.opentargets.org | Disease-target-drug associations, genetic evidence |
| Targets and drugs | ChEMBL | https://www.ebi.ac.uk/chembl | Drug and mechanism resolution |
| Targets and drugs | UniProt, Reactome, STRING | various | Protein and pathway context |
| Literature | PubMed / PMC (E-utilities) | https://pubmed.ncbi.nlm.nih.gov | Publications, abstracts |
| Literature (add) | Europe PMC (includes preprints) | https://europepmc.org | bioRxiv and medRxiv coverage |
| Genetics (add) | GWAS Catalog | https://www.ebi.ac.uk/gwas | Human genetic evidence |
| Regulatory | openFDA: Drugs@FDA and drug labels | https://open.fda.gov | Approvals (original and efficacy supplements) and the current label (indications, boxed warning, clinical studies) of drugs approved against the same target (implemented, `connectors/openfda.py`). Always an analog, never the asset. Adverse-event reports and DailyMed are not read |
| Regulatory (add) | EMA documents | https://www.ema.europa.eu | EU regulatory context |
| Payer and market | CMS Medicare Part D and Part B Spending by Drug | https://data.cms.gov | Spending per beneficiary on approved analogs (implemented, `connectors/pricing.py`); ASP and NADAC are not read |
| Analogs | Open Targets, drugs approved against the target | https://platform.opentargets.org | Which approved drugs count as price analogs (implemented) |
| Epidemiology | NCI State Cancer Profiles | https://statecancerprofiles.cancer.gov | US new cases a year by cancer site: lung, pancreas, colorectal (implemented, `connectors/epidemiology.py`) |
| Epidemiology | CDC Chronic Disease Indicators | https://data.cdc.gov | US adult prevalence: obesity, high blood pressure, asthma (implemented) |
| Epidemiology | Orphanet (Orphadata, CC BY 4.0) | https://www.orphadata.com | Prevalence of rare diseases, by the Orphanet code Open Targets cross-references (implemented) |
| Population | World Bank | https://api.worldbank.org | US population the rates are applied to (implemented) |
| Epidemiology (not read) | SEER, IARC/GCO, WHO | various | SEER needs a key; no documented open API was found for GCO; the WHO API did not answer |
| Company | SEC EDGAR | https://www.sec.gov/edgar | Filings, 8-K exhibits, pipeline statements |
| Company | Tavily | https://tavily.com | Press releases and presentations |
| IP | Google Patents (deep links only) | https://patents.google.com | Patent links; no API |
| Ontologies | MONDO / EFO via Open Targets and EBI OLS | | Disease identity |

Terms of use and attribution requirements: TODO check each source before publishing. Notes seen during research (verify): ClinicalTrials.gov requires attribution; Open Targets is reported as CC0 1.0 in the BioContext listing.

## Known gaps for unapproved drugs

All assets in our test list are unapproved as of 2026-10-03 (list provided by the organizers; re-verify before use).

- **Orange Book / Purple Book** cover approved products only. For unapproved assets, patent and exclusivity information comes from SEC filings and Google Patents links; anything else is `unknown` with an IP-diligence question.
- **openFDA labels and adverse-event data** are empty for unapproved drugs. Safety comes from trial data and, as analogy only, from approved drugs in the same class (labelled as analogy: the source of each such record reads "FDA label of approved analog ...", and its source family is `regulatory_analog`).
- **A label has no history in openFDA.** Only the current text is served, dated by its effective date, so a run replayed before that date does not see the label. Approvals are dated by their own approval day.
- **CMS prices** apply to analogs only. Any price for the candidate is `modeled`.
- **Company coverage varies.** Companies filing 8-Ks on EDGAR give richer text than those filing foreign-issuer forms. A thin result is reported as `not_reported` or `none_found`, never filled from model memory.

## Benchmarks used as priors

| Benchmark | Use | Link |
|---|---|---|
| BIO / Informa / QLS, *Clinical Development Success Rates and Contributing Factors 2011-2020* | Phase-transition and approval base rates by area and modality | https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020 |
| Minikel et al., *Refining the impact of genetic evidence on clinical success*, Nature 2024 | Modifier for genetic support | https://pmc.ncbi.nlm.nih.gov/articles/11096124/ |

Figures quoted in the code and the report must be taken from the primary documents. During research we saw secondary summaries (overall LOA from Phase I of 7.9%; Phase II as the largest hurdle; roughly double LOA with patient preselection biomarkers; 2.6x relative success with genetic support), so verify each against the primary source before use.

TODO: sources for cost per patient by therapeutic area and for pricing analogs.

## Related reading

- Unobio product page for landscape reports: https://unobio.com/diligence
- Open-source MCP servers for biomedical APIs (reference implementations only; our collect phase uses our own deterministic connectors): https://github.com/BioContext, https://github.com/genomoncology/biomcp
