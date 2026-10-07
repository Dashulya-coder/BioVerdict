# BioVerdict: context for coding agents

Read this file, `CONTRIBUTING.md`, and the relevant documents in `docs/` before editing.
Documentation describes the intended product; inspect code and Git branches before claiming
that a feature is implemented or missing. Check current PR status rather than relying on this snapshot.

## Working agreement

- Create a separate branch for each feature, following `arsenii/<task-id>-<short-name>` or
  `dasha/<task-id>-<short-name>`. Use Conventional Commits and open a PR against `main` after
  testing and pushing. Review previous commits for local conventions. Do not merge without authorization.
- Update this file in every implementation PR: behavior, verification, limitations, next steps.
- Ask the user when a material choice is uncertain; give concise options with a recommendation.
  If blocked or unable to substantiate an assumption, stop dependent work and ask instead of guessing.
- Preserve unrelated user changes. Follow the schema approval process in `CONTRIBUTING.md`.
- Treat medical conclusions as evidence-dependent. For new medical facts or live integrations,
  verify current information against authoritative sources; never invent identifiers or citations.
- No network access during reasoning. LLM calls use `llm.call`; failed verification drops claims.
  Keys stay in ignored environment files and must never appear in diffs, logs, or PR descriptions.

## Architecture and references

Python backend: `backend/src/bioverdict/`; React frontend: `frontend/`.
`docs/architecture.md`, `docs/data-model.md`, and `docs/scoring.md` define the pipeline,
contracts, and scoring. `docs/work-plan.md` tracks owners and milestones; `docs/runbook.md`
contains operating commands. Runtime: Python >=3.14, Node 24; use existing lockfiles.

## Implementation snapshot (2026-10-07)

This branch, `arsenii/A5-fixture-cli`, builds on PR #31 (`arsenii/A5-api-fixture`),
which includes the fixture hash work from #14. It is a dependent PR targeting `main`.
The branch contains the store, cache, bundle hashing/versioning, date filters, LLM abstraction,
mechanism/translation reasoning, scoring, and fixture API/report/drill-down/trace/SSE.
Do not equate these branch contents with merged `main`.

- CLI: `bioverdict run --asset divarasib [--as-of YYYY-MM-DD] [--db PATH]
  [--fixtures PATH] [--output PATH]`, also available via `python -m bioverdict`.
  Uses the same fixture pipeline and SQLite records as the API; stdout is a JSON report,
  diagnostics go to stderr. `--output` additionally exports the report. Exit codes: 0 success,
  1 runtime/export failure, 2 invalid arguments or unsupported live mode.
- Fixture mode defaults on; `USE_FIXTURES=0` is rejected. `DB_PATH` and `FIXTURES_DIR`
  are read from the process environment; `.env` is not automatically loaded. Default DB path
  is relative to the working directory. Only divarasib has a complete run fixture.
- The pipeline validates the original fixture hash, filters evidence by the run cutoff,
  rebuilds catalog/hash while keeping citation IDs, drops claims with failed citations,
  and fills missing translation links as unknown. Filtered snapshots mark found sections
  incomplete because evidence has no section mapping. Date filtering cannot reconstruct
  historical revisions of mutable sources or update the static resolver assumptions.
- Fixtures call no external APIs or paid models. Fake calls are not persisted as provider calls.
  Finance outputs remain unavailable; quotation matching does not establish medical entailment.
- Related work exists on other branches: Open Targets #28, Resolver #30, ClinicalTrials.gov
  results/pagination/stopped studies and PubMed #32. Check these before implementing duplicates.
- Frontend remains a scaffold. Live collect orchestration, remaining reasoning modules,
  entailment verification, rNPV/capital, recompute/diff, and the eval runner remain to integrate.

## Verification and next steps

From `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.
From repository root: `uv run --project backend python scripts/check_compat.py` (17 checks).
CLI tests cover real entrypoints, offline execution, SQLite/export, cutoffs including an empty
snapshot, invalid input, failed runs, fixture tampering, and export failure recovery.
Verified on this branch: 369 backend tests pass, Ruff lint and format checks pass (99 Python
files), dependency compatibility 17/17. Existing virtualenv was reused with this branch's source
on `PYTHONPATH`; the complete suite and compatibility check ran outside the sandbox because
FastAPI TestClient hangs inside it. Frontend was not changed in this feature.

Next: review/merge dependencies; integrate the existing Resolver/connectors into live collection,
then build the input/report/evidence UI against the fixture API. Agree each next feature with the user.
