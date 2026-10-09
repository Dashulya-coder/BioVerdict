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
```

| Section | Sources read |
|---|---|
| Mechanism | Open Targets; preprints from Europe PMC |
| Clinical | ClinicalTrials.gov (with posted results); PubMed; full texts of open-access papers (PubMed Central) |
| Competition | ClinicalTrials.gov by target within the indication; openFDA approvals and labels of approved analogs |
| Flags | SEC EDGAR: the sponsor's 8-K and 6-K filings that name the asset |
| Commercial | CMS Medicare spending on analogs; NCI cancer incidence; CDC; Orphanet; World Bank; cBioPortal for how common the asset's mutation is |

Unmet need and IP/regulatory are not searched and say so. Source rules and attribution:
[`docs/sources.md`](docs/sources.md).

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
| `LLM_MAX_INPUT_CHARS` | Largest request the gateway accepts, in characters; see [`docs/cost.md`](docs/cost.md) |
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
        → Reason (four modules, no network) → Grounding (code) → Scoring (code) → Report
```

- **Resolver.** One model call reads the text; every identifier comes from a database lookup.
  What was inferred is listed as an assumption.
- **Collect.** A fixed list of connectors per section, with limits on requests, records and time.
  Extraction picks verbatim quotes; status records (a trial's status, an approval, a spending
  row) are stored whole without a model.
- **Reason.** Mechanism, clinical, competition and translation-chain modules write claims with
  quotes over the frozen bundle only.
- **Scoring.** Confidence per claim, hard and soft gates, probability of success, rNPV by Monte
  Carlo, verdict.

Designed and not built yet: triage, Bull vs Bear, Chair with targeted second rounds, the
entailment judge. Details: [`docs/architecture.md`](docs/architecture.md).
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
- Four reasoning modules, code grounding, deterministic scoring and verdict, probability of
  success and rNPV with capital, time to milestone and a tornado (`GET /runs/{id}/financials`).
- API with report, drill-down, trace, progress events, market size, add-evidence and diff; CLI
  with `run`, `eval`, `warm`, `doctor`.
- Web workspace: input, resolved assumptions, evidence explorer, sources, comparing runs and
  adding a document; the report screen with the executive verdict, the translation chain and
  claim drill-down to verbatim quotes.
- Two model adapters (Anthropic, and an OpenAI-compatible gateway), with cache, budget, deadline
  and failover.
- Docker images, `compose.yaml`, and CI that lints, tests and runs a fixture run through the
  containers.

**Not yet**

- **No whole run with a real model has been measured**: quality, cost and time are unknown.
- The trace panel, and on the report screen the gates list, the ranked diligence questions and
  the tornado chart.
- rNPV is not calibrated: peak share, rebates, margin, discount rate and phase costs and
  durations are placeholders listed with every result, so its figures are modeled, not sourced.
- The independent entailment judge, Bull/Bear and Chair, unmet-need, commercial and IP modules.
- Real evaluation cases, the closed-book leakage probe and baselines: the case file holds one
  smoke case.
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

Nothing is measured yet; this table is filled from `eval/results/` after the first evaluation
run with a real model. Template: [`docs/eval.md`](docs/eval.md).

| Metric | Result |
|---|---|
| Citation support rate | not measured |
| Source validity | not measured |
| Verdict stability (3 runs) | not measured |
| Verdict change on strong counter-evidence | not measured |
| Median cost per run | not measured |
| Median time per run | not measured |

## Team

| Person | Track |
|---|---|
| Arsenii | A: Evidence and platform (resolver, connectors, bundle, API, evidence UI, recompute, eval harness) |
| Dasha | B: Reasoning and verdict (LLM layer, reasoning modules, scoring, verification, report UI, eval cases) |

Details: [`docs/work-plan.md`](docs/work-plan.md).

## License

TODO: choose a license and check hackathon rules before making the repository public.
