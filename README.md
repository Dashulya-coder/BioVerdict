# BioVerdict

**An evidence-first AI investment committee for biotech underwriting.**

Input: an indication and a mechanism (or a drug name / code).
Output: an Investment Underwriting Report with a verdict of **Invest / Conditional / Do Not Invest**, in which every conclusion traces back through
`Recommendation → Claims → Evidence → Sources`.

> Not investment advice. This is a research prototype built for a hackathon. Every number is either quoted from a source or labelled as a model assumption.

## Why this is different

Most "AI due diligence" output looks confident whether it is right or wrong. We designed around that failure.

1. **Closed world.** The network is touched once, in a *collect* phase. The results are frozen into a content-hashed evidence bundle. The *reasoning* phase has no network access: if a fact is not in the bundle, it does not exist for this run.
2. **Grounded or dropped.** Every claim carries a verbatim quote. A verifier keeps the claim only if the quote appears in the bundle. URLs and IDs are accepted only if they were actually fetched in this run.
3. **Unknown is a result.** Missing information is reported with a reason (`not_reported`, `none_found`, `not_searched`, `error`) and becomes a diligence question that names what kind of data would answer it.
4. **Code decides, the LLM classifies.** Confidence, probability of success, rNPV, capital and the verdict are computed by deterministic code from the claim ledger.
5. **New evidence changes the verdict.** Adding a document triggers an incremental recompute and shows a before/after diff.

## Quick start

Prerequisites: Python 3.14, [`uv`](https://docs.astral.sh/uv/), Node 24 LTS and [`pnpm`](https://pnpm.io/) (see [`docs/stack.md`](docs/stack.md)).

```bash
git clone <repo-url> bioverdict && cd bioverdict
cp .env.example .env            # add API keys, see "Configuration"
cd backend && uv sync
uv run python ../scripts/check_compat.py   # expects "17/17 checks passed"
uv run uvicorn bioverdict.api.main:app --reload      # API on :8000
cd ../frontend && pnpm install && pnpm dev            # UI on :5173
```

Run one underwriting through the API. Until the live pipeline is wired in, runs are answered from
`fixtures/` (`USE_FIXTURES=1`, the default); the only fixture so far is `divarasib`:

```bash
curl -s -X POST localhost:8000/runs -H 'content-type: application/json' -d '{"asset": "divarasib"}'
curl -s localhost:8000/runs/<run_id>/report      # executive verdict, claims, chain, sources
curl -N localhost:8000/runs/<run_id>/events      # progress as server-sent events
```

The routes and response shapes are described in [`docs/architecture.md`](docs/architecture.md)
(section 12); a running server also serves them at `/docs`. Run the same fixture pipeline without
starting the server (from `backend/`, no API keys needed):

```bash
uv run bioverdict run --asset divarasib --as-of 2026-10-07 --output report.json
```

The JSON report goes to stdout and the optional output file; diagnostics go to stderr. Runs are
saved to SQLite, shared with the API when both use the same `DB_PATH`. Use `--db` and `--fixtures`
to override paths. `python -m bioverdict` provides the same CLI. The current fixture snapshot is
static; an earlier cutoff filters evidence and drops claims whose citations no longer verify.
This is an offline demo, not a live underwriting. Export environment variables explicitly;
the CLI does not automatically load `.env`.

Full operating procedures, including cache pre-warm and demo-day fallbacks: [`docs/runbook.md`](docs/runbook.md).

## Configuration

| Variable | Purpose |
|---|---|
| `LLM_PRIMARY` | Primary provider and model per step, see [`docs/cost.md`](docs/cost.md) |
| `LLM_FALLBACKS` | Ordered failover list |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` | Provider keys (never commit) |
| `NCBI_API_KEY`, `TAVILY_API_KEY`, `SEC_USER_AGENT` | Data-source access |
| `RUN_BUDGET_USD`, `RUN_TIMEOUT_S` | Hard limits per run |
| `DB_PATH`, `CACHE_DIR` | SQLite file and HTTP/LLM cache |

## How it works

```
Resolver → Triage → Collect (parallel agents) → FREEZE bundle → Reason (Bull/Bear/Chair, no network)
        → Scoring (code) → Verification → Report
```

Details: [`docs/architecture.md`](docs/architecture.md). Data contracts: [`docs/data-model.md`](docs/data-model.md). Verdict logic: [`docs/scoring.md`](docs/scoring.md).

## Documentation

| Doc | Content |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Pipeline, agents, evidence store, failure handling, API |
| [`docs/stack.md`](docs/stack.md) | Toolchain, versions, pinning policy, project skeleton |
| [`docs/design-system.md`](docs/design-system.md) | Approved dark-console palette, typography, shared UI and frontend conventions |
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

- [x] P0: schema, evidence store with versions and `as_of`, deterministic scoring, resolver
- [ ] P0: eval set
- [ ] P1: five core agents (mechanism and translation done), connectors (ClinicalTrials.gov and Open Targets done; PubMed and openFDA pending), executive verdict and drill-down API (done, on fixtures), drill-down UI, trace and cost panel
- [ ] P1: incremental re-underwrite, diff screen, "add evidence"
- [ ] P2: Bull/Bear, targeted second round, translation chain graph, diligence ranking by value of information
- [ ] P3: IP/CMC, red/green flags, market sentiment, more playbooks

## Results

TODO: fill from `eval/results/` after the evaluation run. Table template is in [`docs/eval.md`](docs/eval.md).

| Metric | Result |
|---|---|
| Citation support rate | TODO |
| Source validity | TODO |
| Verdict stability (3 runs) | TODO |
| Verdict change on strong counter-evidence | TODO |
| Median cost per run | TODO |
| Median time per run | TODO |

## Team

| Person | Track |
|---|---|
| Arsenii | A: Evidence and platform (resolver, connectors, bundle, API, evidence UI, recompute, eval harness) |
| Dasha | B: Reasoning and verdict (LLM layer, reasoning modules, scoring, verification, report UI, eval cases) |

Details: [`docs/work-plan.md`](docs/work-plan.md).

## License

TODO: choose a license and check hackathon rules before making the repository public.
