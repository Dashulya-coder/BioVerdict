# Runbook

For whoever operates the system: setup, normal operations, evaluation, demo day, and what to do when something breaks. Commands marked TODO are not implemented yet.

## 1. Setup

Prerequisites: Python 3.14, `uv`, Node 24 LTS, git (see `stack.md` for versions and pinning).

```bash
cp .env.example .env
# fill in keys; never commit .env
cd backend && uv sync
cd ../frontend && pnpm install
```

Required variables are listed in the README. Check access:

```bash
uv run python ../scripts/check_compat.py   # dependencies work on this Python (expects 17/17)
uv run bioverdict doctor        # TODO: verifies keys, network, DB, cache dir
```

## 2. Start

```bash
cd backend && uv run uvicorn bioverdict.api.main:app --reload
cd frontend && pnpm dev:api     # the workspace runs analyses on the API at 127.0.0.1:8000
cd frontend && pnpm dev         # or: the prepared Divarasib snapshot, no backend, no network
```

`pnpm dev:api` is `vite --mode api`; set `VITE_API_URL` to use another address (it also turns
the API on for a plain `pnpm dev` or `pnpm build`). The header shows where an analysis came from:
`Demo mode` (snapshot), `Fixture run` or `Live run` (what the API's `/health` reports), with the
run id. The workspace follows a run until its evidence is frozen and then shows the resolved
input and the whole bundle; reasoning and scoring continue in the backend under that run id.
The API must allow the page's origin: `CORS_ORIGINS` defaults to `http://localhost:5173`.

## 3. Run an underwriting

For the independent A4 collection-only demo (no underwriting or paid calls), run from the
repository root:

```bash
uv run --project backend python scripts/collect_fixture.py --db /tmp/a4.sqlite
```

See [collection](collection.md) for cutoffs, statuses and limits. The full underwriting, from
`backend/`:

```bash
uv run bioverdict run --asset divarasib --output report.json  # offline fixture demo
uv run bioverdict run --asset divarasib --as-of 2026-06-30    # time-travel on the fixture
# Live: public sources and paid model calls
USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --asset HRO761 --output report.json
USE_FIXTURES=0 uv run --env-file ../.env bioverdict run --query "KRAS G12C inhibitor in NSCLC"
```

### Live runs (`USE_FIXTURES=0`)

The same steps, events, SQLite records and report as a fixture run, from real sources:

1. **Resolve.** One model call reads the text; every id comes from Open Targets. What was not
   confirmed is listed in the report's assumptions. No identifiable target fails the run.
2. **Collect.** Mechanism: Open Targets. Clinical: ClinicalTrials.gov (by asset) and PubMed.
   Competition: ClinicalTrials.gov by target within the indication. One extraction call per
   source that returned records. Other sections stay `not_searched`.
3. **Freeze**, then **reason** and **score** on the frozen bundle only.

Needs `ANTHROPIC_API_KEY`; without it the API answers 503 and the CLI exits 2 before a run is
created. `RUN_BUDGET_USD` and `RUN_TIMEOUT_S` cap one run; the deadline counts from its first
model call. `NCBI_API_KEY` is optional. Source answers are cached in SQLite and model answers in
`CACHE_DIR/llm`, so a repeated run is cheap and gives the same bundle hash. The API takes
`{"asset": ...}` or `{"indication": ..., "mechanism": ...}`; start the server with
`USE_FIXTURES=0 uv run --env-file ../.env uvicorn bioverdict.api.main:app`.

A run fails, with the reason in its last event, when no target is identified, when every planned
source of a section failed and nothing was collected, or when the budget, the deadline or the
model configuration stops it. Unexpected errors are recorded by class name only; the text is in
the server log. A section that was cut short (more than 50 records or 24,000 characters per
source, a rejected quote, a source error) is `incomplete`, never `found`.

Checked so far: offline tests with stand-in sources and model, and runs against the three real
sources with a stand-in model. A run with a real model has not been measured yet (cost, time,
extraction and reasoning quality).

The fixture CLI writes run status, progress events, bundle, evidence and claims to SQLite, and
returns the API's JSON report on stdout (also in `--output` if supplied). Diagnostics use stderr.
No network or paid model calls occur; provider-call totals are zero. Exit codes are 0 for success,
1 for run/export failure and 2 for invalid input or unsupported live mode. A failed export leaves
the completed run in SQLite. Use an existing output directory.

`--as-of` filters the static fixture by publication date (or retrieval date for undated records),
rebuilds the bundle hash/catalog and drops claims with failed citations. Previously found sections
become incomplete when evidence is filtered. This cannot reconstruct historical source revisions
or refresh resolver assumptions. Only `divarasib` has a fixture; `doctor`, `warm` and `eval` remain
TODO. Export environment variables explicitly or use `uv run --env-file`; `.env` is not auto-loaded.

## 4. Pre-warm the cache

Retrieval is free and should be cached for every test-list asset and related targets. LLM runs are paid; warm them only for demo and eval assets.

```bash
uv run bioverdict warm --retrieval --list data/assets_all.txt   # TODO
uv run bioverdict warm --llm --list data/assets_demo.txt        # TODO
```

## 5. Run evaluation

```bash
uv run bioverdict eval --cases eval/cases.yaml --out eval/results/$(date +%F)   # TODO
```

Compare the verdict distribution and top risks with expectations. Log any change to weights or thresholds in `config/scoring.yaml` with a reason.

## 6. Reset

```bash
rm -f data/bioverdict.sqlite     # removes all runs; keep data/cache/
```

Share demo state with a dump (`sqlite3 .dump`), not by sharing the live file.

## 7. Demo-day checklist

T-24h:

- [ ] Freeze code (date and time in `CONTRIBUTING.md`).
- [ ] Pre-warm caches; run every demo asset end to end.
- [ ] Record bundle hashes of the demo runs.
- [ ] Check provider balances and rate limits; confirm failover works with a deliberately bad key in a test.

T-1h:

- [ ] Both machines run the same commit.
- [ ] Network check; hotspot as a backup.
- [ ] Open the UI at the demo run; check trace and cost panel.
- [ ] Browser tabs ready: report, diff screen, sources.

During: if something fails, use the fallbacks in `demo-script.md`.

## 8. Failure playbook

| Symptom | Likely cause | Action |
|---|---|---|
| Run stalls at Collect | source down or rate limit | check the trace; section is marked `error`/`incomplete`; the run still completes |
| Many claims dropped | quote not found in bundle | inspect `verification_log`; check the extraction prompt and document truncation |
| Verdict flips between runs | non-determinism | check temperature, model versions, mixed-model flag, cache misses |
| Cost spike | high reasoning effort or retry loop | check `llm_calls`; lower effort; confirm the budget cap |
| 429 or quota errors | provider limits | failover should engage; reduce parallelism |
| 401 or 403 | bad key | fix the key; the system must not fail over silently on auth errors |
| Empty section for a known drug | wrong resolver ID | check the Resolver output; disambiguate by ID |
| Time-travel result looks "too informed" | leakage from model memory | check claims without evidence in the bundle; confirm the gate is on |

## 9. Escalation

| Area | Contact |
|---|---|
| Connectors, cache, bundle, API, evidence UI, recompute | Arsenii |
| LLM layer, reasoning, scoring, verification, report UI | Dasha |
| Organizers | TODO |
