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
| Literature | PubMed Central open-access subset (NCBI BioC service) | https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/ | The Results section and the tables of up to four papers PubMed found, those that name the asset first (implemented, `connectors/pmc.py`). Only papers under CC BY or CC0: a paper under a non-commercial or no-derivatives licence is left with its abstract |
| Literature | PubMed practice guidelines for the indication | https://pubmed.ncbi.nlm.nih.gov | The newest eight papers PubMed labels `Practice Guideline` or `Guideline` whose title names treatment, therapy or management (without that filter the newest guidelines of a disease are about imaging), read by their title and abstract for the standard of care (implemented, `connectors/pubmed_guidelines.py`). The indication is searched unquoted so that PubMed maps it to its MeSH heading; a guideline is a consensus statement, so its level is a guess (`human_observational`) and each counts as its own independence group |
| Literature | Europe PMC, preprints only | https://europepmc.org | bioRxiv, medRxiv and other preprint servers, which PubMed does not carry (implemented, `connectors/europepmc.py`). Weakest evidence level and source kind `preprint`; a preprint is not linked to its later paper |
| Genetics (add) | GWAS Catalog | https://www.ebi.ac.uk/gwas | Human genetic evidence |
| Regulatory | openFDA: Drugs@FDA and drug labels | https://open.fda.gov | Approvals (original and efficacy supplements) and the current label (indications, boxed warning, clinical studies) of drugs approved against the same target (implemented, `connectors/openfda.py`). Always an analog, never the asset. Adverse-event reports and DailyMed are not read |
| Regulatory (add) | EMA documents | https://www.ema.europa.eu | EU regulatory context |
| Payer and market | CMS Medicare Part D and Part B Spending by Drug | https://data.cms.gov | Spending per beneficiary on approved analogs (implemented, `connectors/pricing.py`); ASP and NADAC are not read |
| Analogs | Open Targets, drugs approved against the target | https://platform.opentargets.org | Which approved drugs count as price analogs (implemented) |
| Epidemiology | NCI State Cancer Profiles | https://statecancerprofiles.cancer.gov | US new cases a year by cancer site: lung, pancreas, colorectal (implemented, `connectors/epidemiology.py`) |
| Epidemiology | cBioPortal: MSK-IMPACT Clinical Sequencing Cohort (Zehir et al., Nat Med 2017) | https://www.cbioportal.org | How many patients of a cancer type carry the asset's variant: lung (non-small cell), pancreas, colorectal (implemented, `connectors/biomarker.py`). Point mutations of a target gene only; one referral centre's patients, mostly with advanced disease |
| Epidemiology | CDC Chronic Disease Indicators | https://data.cdc.gov | US adult prevalence: obesity, high blood pressure, asthma (implemented) |
| Epidemiology | Orphanet (Orphadata, CC BY 4.0) | https://www.orphadata.com | Prevalence of rare diseases, by the Orphanet code Open Targets cross-references (implemented) |
| Population | World Bank | https://api.worldbank.org | US population the rates are applied to (implemented) |
| Epidemiology (not read) | SEER, IARC/GCO, WHO | various | SEER needs a key; no documented open API was found for GCO; the WHO API did not answer |
| Company | SEC EDGAR: company list, `data.sec.gov` submissions, filing archives | https://www.sec.gov/edgar | The newest 8-K and 6-K filings of the asset's sponsor and their press-release exhibits; only the paragraphs that name the asset (implemented, `connectors/edgar.py`). The sponsor comes from the registry and its CIK from the SEC's company list, by whole name. Full-text search is not used: it refuses automated requests. Needs `SEC_USER_AGENT` |
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
- **A company statement is not a finding.** A filing has source kind `company` and the level `registry_record`: it can support a fact about a program (stopped, started, designated) and adds no weight to a claim that the drug works. It shares the sponsor's independence group with the registry records.
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
