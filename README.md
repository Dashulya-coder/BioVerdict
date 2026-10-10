# BioVerdict

**An evidence-first AI investment committee for biotech underwriting.**

Input: an indication and a mechanism (or a drug name / code).
Output: an Investment Underwriting Report with a verdict of **Invest / Conditional / Do Not Invest**, in which every conclusion traces back through
`Recommendation → Claims → Evidence → Sources`.

> Not investment advice. This is a research prototype built for a hackathon. Every number is either quoted from a source or labelled as a model assumption.

## Why this is different

Most "AI due diligence" output looks confident whether it is right or wrong. We designed around that failure.

1. **Closed world.** The network is touched once, in a *collect* phase. The results are frozen into a content-hashed evidence bundle. The *reasoning* phase has no network access: if a fact is not in the bundle, it does not exist for this run.
2. **Grounded or dropped.** Every claim carries a verbatim quote. Code keeps the claim only if the quote appears in the evidence it names; a claim with a failed citation is dropped, not softened. URLs and IDs come from retrieval, never from a model.
3. **Unknown is a result.** Missing information is reported with a reason (`not_reported`, `none_found`, `not_searched`, `error`, `incomplete`) and becomes a diligence question that names what kind of data would answer it.
4. **Code decides, the LLM classifies.** Claim confidence, the gates, the probability of success, the market size and the verdict are computed by deterministic code from the claim ledger. A model never produces a number the verdict depends on.
5. **New evidence changes the verdict.** Adding a document starts a recompute as a new run: the model only places the new evidence on existing claims, code recomputes, and a diff shows what moved.

## Quick start

### With Docker

Needs only Docker. From the repository root:

```bash
docker compose up --build                 # open http://localhost:8080
python3 scripts/check_containers.py       # optional: one run, the page and CORS, end to end
```

Runs are answered offline from the prepared Divarasib fixture: no keys, no network, no cost.
For live runs put the keys into `.env` (see "Configuration") and start with
`USE_FIXTURES=0 docker compose up`. Details: [`docs/runbook.md`](docs/runbook.md), "Docker".

### From source

Prerequisites: Python 3.14, [`uv`](https://docs.astral.sh/uv/), Node 24 LTS and [`pnpm`](https://pnpm.io/) (see [`docs/stack.md`](docs/stack.md)).

```bash
git clone <repo-url> bioverdict && cd bioverdict
cp .env.example .env            # add API keys, see "Configuration"
cd backend && uv sync
uv run python ../scripts/check_compat.py   # expects "17/17 checks passed"
uv run bioverdict doctor                   # is this machine ready: keys, caches, sources
uv run uvicorn bioverdict.api.main:app --reload      # API on :8000
cd ../frontend && pnpm install && pnpm dev:api        # UI on :5173, running analyses on the API
# `pnpm dev` instead opens the prepared Divarasib snapshot: no backend, no network
```

### One underwriting

Through the API. By default runs are answered from `fixtures/` (`USE_FIXTURES=1`, offline and
free); the only fixture so far is `divarasib`:

```bash
curl -s -X POST localhost:8000/runs -H 'content-type: application/json' -d '{"asset": "divarasib"}'
curl -s localhost:8000/runs/<run_id>/report      # executive verdict, claims, chain, sources
curl -s localhost:8000/runs/<run_id>/market      # patients, analog price, market size
curl -N localhost:8000/runs/<run_id>/events      # progress as server-sent events
```

The routes and response shapes are described in [`docs/architecture.md`](docs/architecture.md)
(section 12); a running server also serves them at `/docs`. The same pipeline without a server
(from `backend/`, no keys needed):

```bash
uv run bioverdict run --asset divarasib --as-of 2026-10-07 --output report.json
```

The JSON report goes to stdout and the optional output file; diagnostics go to stderr. Runs are
saved to SQLite, shared with the API when both use the same `DB_PATH`. An earlier `--as-of`
filters the evidence by date and drops claims whose citations no longer verify.

### Live runs

With `USE_FIXTURES=0` a run reads the public sources below, freezes what it found and calls the
configured model, which costs money. It takes a drug name or code, or free text:

```bash
USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --asset HRO761 --output report.json
USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --query "KRAS G12C inhibitor in NSCLC"
USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --query "BTK inhibitor for multiple sclerosis"
```

| Section | Sources read |
|---|---|
| Unmet need | PubMed: the newest practice guidelines for the indication |
| Mechanism | Open Targets; preprints from Europe PMC |
| Clinical | ClinicalTrials.gov (with posted results); PubMed, including safety reviews of the class; full texts of open-access papers (PubMed Central) |
| Competition | ClinicalTrials.gov by target within the indication; openFDA approvals and labels of approved analogs and of the drugs approved for the indication; the EMA register of medicines |
| Flags | SEC EDGAR: the sponsor's 8-K and 6-K filings that name the asset |
| Commercial | CMS Medicare spending on analogs; NCI cancer incidence; CDC; Orphanet; World Bank; cBioPortal for how common the asset's mutation is |

Translation is reasoned from the mechanism and clinical evidence. IP/regulatory is not searched
and says so. Source rules and attribution: [`docs/sources.md`](docs/sources.md).

Environment variables are not loaded from `.env` automatically outside Docker: pass `--env-file`
to `uv run` or export them.

### Other commands

```bash
uv run bioverdict eval --cases ../eval/cases.yaml --out ../eval/results/<date>   # regression cases and metrics
uv run bioverdict warm --list ../eval/assets_example.tsv                         # fill the source cache, no model
uv run bioverdict doctor                                                         # readiness of this machine
```

Full operating procedures, including cache pre-warm and demo-day fallbacks: [`docs/runbook.md`](docs/runbook.md).

## Configuration

| Variable | Purpose |
|---|---|
| `USE_FIXTURES` | `1` (default): runs are answered offline from fixtures. `0`: live runs |
| `LLM_PROVIDER` | `anthropic` or `openai` (the organizers' gateway). Unset: the one whose key is set |
| `ANTHROPIC_API_KEY` | Key of Anthropic's own API (never commit) |
| `TEAM_API_KEY`, `LLM_BASE_URL` | Key and base URL of the OpenAI-compatible gateway; `OPENAI_API_KEY` is used when `TEAM_API_KEY` is empty |
| `LLM_MAX_INPUT_CHARS` | Largest request the gateway accepts, in characters (unset: no limit); see [`docs/cost.md`](docs/cost.md) |
| `LLM_MAX_CONCURRENCY` | Requests sent to the gateway at once (default 3); more wait their turn |
| `NCBI_API_KEY`, `OPENFDA_API_KEY` | Optional: higher request limits of PubMed and openFDA |
| `SEC_USER_AGENT` | "Name email", the contact the SEC asks for; without it company filings are not read |
| `RUN_BUDGET_USD`, `RUN_TIMEOUT_S` | Hard limits per run |
| `RECOMPUTE_MODE` | How added evidence is recomputed: `classify` (default) or `full` |
| `DB_PATH`, `CACHE_DIR`, `HTTP_CACHE_MAX_AGE_H` | SQLite file, HTTP/LLM cache, and how long a source answer is reused (unset: for ever) |
| `CORS_ORIGINS` | Origins the API accepts from a browser |

`GEMINI_API_KEY` and `TAVILY_API_KEY` are in `.env.example` and are not read by any code yet.
The full list with comments is [`.env.example`](.env.example).

## How it works

```
Resolver → Collect (one bounded tool loop per section) → FREEZE bundle
        → Reason (six modules, no network) → Grounding (code) → Skeptic → Judge
        → Scoring (code) → Chair → Synthesis → Report
```

- **Resolver.** One model call reads the text; every identifier comes from a database lookup.
  What was inferred is listed as an assumption.
- **Collect.** A fixed list of connectors per section, with limits on requests, records and time.
  Extraction picks verbatim quotes; status records (a trial's status, an approval, a spending
  row) are stored whole without a model.
- **Reason.** Unmet need, mechanism, translation chain, clinical, competition and commercial
  modules write claims with quotes over the frozen bundle only.
- **Skeptic and judge.** The Skeptic looks for evidence against the claims; a grounded objection
  becomes a contradicting link. An entailment judge reads each quote with its passage and removes
  a link the quote does not support.
- **Scoring.** Confidence per claim, hard and soft gates, an answer per module, probability of
  success, rNPV by Monte Carlo, verdict.
- **Chair.** Asks the questions only diligence could settle; code ranks them by how much each
  answer could move the verdict.
- **Synthesis.** Writes the scientific and translation theses, the next-trial plan, the
  competitive and commercial view and the investment case from the claims and code's figures;
  code keeps a sentence only if it cites claims and its numbers come from them or from code.

Designed and not built yet: triage, Bull vs Bear, the Chair's targeted second collection round.
Details: [`docs/architecture.md`](docs/architecture.md).
Data contracts: [`docs/data-model.md`](docs/data-model.md). Verdict logic: [`docs/scoring.md`](docs/scoring.md).

## Documentation

| Doc | Content |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Pipeline, agents, evidence store, failure handling, API |
| [`docs/stack.md`](docs/stack.md) | Toolchain, versions, pinning policy, project skeleton |
| [`docs/design-system.md`](docs/design-system.md) | Approved dark editorial palette, typography, shared UI and frontend conventions |
| [`docs/data-model.md`](docs/data-model.md) | Evidence, Claim, Bundle, statuses, SQLite schema |
| [`docs/scoring.md`](docs/scoring.md) | Gates, confidence, probability of success, rNPV, capital |
| [`docs/sources.md`](docs/sources.md) | Data sources, attribution, source-order rules |
| [`docs/eval.md`](docs/eval.md) | Evaluation plan and results |
| [`docs/cost.md`](docs/cost.md) | Models, pricing, cost per run |
| [`docs/domain-pack-oncology.md`](docs/domain-pack-oncology.md) | Domain-specific playbook (RAS/KRAS and WRN) |
| [`docs/demo-script.md`](docs/demo-script.md) | Final demo walkthrough |
| [`docs/runbook.md`](docs/runbook.md) | Setup, operations, failure playbook |
| [`docs/collection.md`](docs/collection.md) | A4 bounded collection, grounding, limits and offline demo |
| [`docs/limitations.md`](docs/limitations.md) | What the system cannot know |
| [`docs/glossary.md`](docs/glossary.md) | Terms and abbreviations |
| [`docs/decisions/`](docs/decisions/) | Architecture decision records |
| [`docs/work-plan.md`](docs/work-plan.md) | Role split, task lists, milestones, ownership |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Team workflow |

## Status

Task by task, with owners: [`docs/work-plan.md`](docs/work-plan.md). In short:

**Works**

- Resolver, connectors for every source in the table above, bounded collection with grounded
  extraction, cache, `as_of` cutoff, frozen and hashed bundles.
- Six reasoning modules, code grounding, the Skeptic, the entailment judge and the Chair;
  deterministic scoring, an answer per module and the verdict; probability of success and rNPV
  with capital, time to milestone and a tornado (`GET /runs/{id}/financials`).
- API with report, drill-down, trace, progress events, market size, add-evidence and diff; CLI
  with `run`, `eval`, `warm`, `doctor`, `sensitivity` and `cost`.
- Web workspace: input, resolved assumptions, evidence explorer, sources, comparing runs and
  adding a document; the report screen with the executive verdict, six module answers, gates,
  the translation chain, ranked diligence questions, the tornado and claim drill-down to
  verbatim quotes; the trace screen with the cost and every model call of a run.
- Two model adapters (Anthropic, and an OpenAI-compatible gateway), with cache, budget, deadline
  and failover.
- Docker images, `compose.yaml`, and CI that lints, tests and runs a fixture run through the
  containers.

**Not yet**

- Whole runs with a real model have been made for one question only (BTK inhibitor x multiple
  sclerosis), one run per code version: stability across runs is not measured.
- The written theses (including the next-trial plan and the investment case) are a model's
  synthesis checked for citations and numbers, not for meaning.
- rNPV is not calibrated: peak share, rebates, margin, discount rate and phase costs and
  durations are placeholders listed with every result, so its figures are modeled, not sourced.
  Multiple sclerosis has no patient count in the sources, so it has no market size and no rNPV.
- On the gateway the judge is a model of the same vendor as the one that writes the claims.
- Bull/Bear, the IP/regulatory module and patent sources.
- The closed-book leakage probe and baselines.
- The API has no authentication: do not expose a live instance, anyone could spend the model
  key.

What the system cannot know at all: [`docs/limitations.md`](docs/limitations.md).

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
uv run --project backend python scripts/check_compat.py     # from the repository root
cd frontend && pnpm lint && pnpm typecheck && pnpm format:check && pnpm build
```

CI runs the same on every pull request.

## Results

Live runs of BTK inhibitor x multiple sclerosis on 2026-10-10, on the organizers' gateway. One
question, so these describe that question, not the system in general. Details and method:
[`docs/eval.md`](docs/eval.md), section 9; costs: [`docs/cost.md`](docs/cost.md).

| Metric | Result |
|---|---|
| Cost per run | about $3.10 with the whole bundle read (`R-0cb20fbb…` $3.07, the written case $0.04 more); $0.87 to $1.78 on earlier versions that read part of it |
| Time per run | about 9 minutes (486 s, and 37 s for the written case); 3 min 45 s to 7 min 21 s before |
| Model calls per run | 78: extraction, six modules in up to eight batches each, Skeptic, judge, Chair, synthesis |
| Quotes found verbatim in their source | all kept quotes: code drops a claim whose quote is not in the evidence it names |
| Evidence read by the modules | none of the bundle's 214 items left out of a module's prompts for length (market records go to code, not to a model); 11 of 11 registry trials and 29 of 29 drug records approved for MS cited by a claim |
| Quotes the judge confirmed | 220 of 233 judged links (13 removed); 40% were removed before results were stored as lines (#124, #125) |
| Written case | 24 sentences in six theses, none dropped by code for an uncited claim or a number of its own |
| Sensitivity benchmark | 3 of 5 cases passed, on a base as of 2024-06-30, on an earlier version; not re-run since |
| Verdict change on strong counter-evidence | shown: evobrutinib as of 2023-11-30 goes from Conditional to Do Not Invest (gate K1) when the two reports of its failed phase 3 are added; one source on a clinical hold leaves it Conditional (`eval/sensitivity-evobrutinib.yaml`) |
| Verdict stability | not measured (the verdict was Conditional on every run of the day) |

## What the brief asks for, and where it is

| Deliverable | Where |
|---|---|
| Working prototype: indication + mechanism in, investment underwriting out | the New analysis screen (indication and mechanism; the drug is optional); `bioverdict run --query "BTK inhibitor for multiple sclerosis"`; `POST /runs` |
| Interactive evidence: recommendation to claims to evidence to sources | Report: the verdict's top risks, gates, six module answers and the written theses each open their claims; a claim opens its verbatim quote and the source link (`GET /runs/{id}/claims/{claim}`, `/evidence/{id}`) |
| Architecture | [`docs/architecture.md`](docs/architecture.md), [`docs/data-model.md`](docs/data-model.md), [`docs/scoring.md`](docs/scoring.md) |
| README | this file |
| Source attribution | [`docs/sources.md`](docs/sources.md); every evidence item keeps its source, URL, record id and date |
| Model and API usage | [`docs/cost.md`](docs/cost.md) (models by step, gateway limits); "Configuration" above |
| Approximate cost per run | "Results" above; [`docs/cost.md`](docs/cost.md), measured from the `llm_calls` table; `bioverdict cost` |
| Logs and traces | the Trace screen (every model call with model, time, tokens, cost, cache hit, failover), `GET /runs/{id}/trace`, the run's progress events (`/runs/{id}/events`), `verification_log` |
| Demo: new or contradictory evidence changes the conclusion | Compare: add a document or compare two cutoffs; the diff names each module that moved and the quote that moved it; evobrutinib goes from Conditional to Do Not Invest on the reports of its failed phase 3 ([`docs/demo-script.md`](docs/demo-script.md), step 5a) |

## Team

| Person | Track |
|---|---|
| Arsenii | A: Evidence and platform (resolver, connectors, bundle, API, evidence UI, recompute, eval harness) |
| Dasha | B: Reasoning and verdict (LLM layer, reasoning modules, scoring, verification, report UI, eval cases) |

Details: [`docs/work-plan.md`](docs/work-plan.md).

## License

TODO: choose a license and check hackathon rules before making the repository public.
