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

This branch, `arsenii/A5-research-workspace`, builds on the shared frontend foundation in #34
(`arsenii/A5-design-system`, 28aa059), with a PR targeting `main`. Merge #34 first; the
remaining changes are the functional research workspace. Backend fixture API #31
and CLI #33 remain separate open PRs; #33 builds on #31 and the fixture hash work from #14.
The descriptions below of CLI/API behavior refer to those PRs, not merged `main`.

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
- Frontend foundation: Tailwind CSS 4 via the Vite plugin, semantic color tokens, local Inter,
  shared typed UI primitives, strict TypeScript, type-aware ESLint, and Prettier/Tailwind sorting.
  The user approved the dark analytical-console direction in Canva and English UI.
  See `docs/design-system.md` for the shared contract with Dasha. Use Tailwind and small
  decomposed components for new UI.
- Frontend research workspace: English input → resolved assumptions → evidence explorer,
  plus grouped original sources, source/type/search filters, verbatim excerpts, dates and links.
  Demo aliases: Divarasib, GDC-6036, RG-6330. The cutoff cannot exceed 2026-10-07; undated
  evidence uses retrieval date. This is a view filter, not historical reconstruction or underwriting.
  Reads the existing root Divarasib fixture; the static resolver fixture comes from #31.
  Zod validates data only when the user opens a demo; data/validator code is a lazy chunk.
  Error states support editing or page reload; obsolete loads are ignored after reset/unmount.
  No backend/API/model calls and no bundle-hash verification in this UI. API data shapes are
  not inferred from these demo-only view models. Future integration belongs in the app client.
- `docs/work-plan.md` now distinguishes merged components, partially implemented tasks,
  pending PRs and remaining scope for both tracks. Counts describe whole tasks, not effort.
- Live collect orchestration, remaining reasoning modules,
  entailment verification, rNPV/capital, recompute/diff, and the eval runner remain to integrate.

## Verification and next steps

From `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.
From repository root: `uv run --project backend python scripts/check_compat.py` (17 checks).
CLI tests cover real entrypoints, offline execution, SQLite/export, cutoffs including an empty
snapshot, invalid input, failed runs, fixture tampering, and export failure recovery.
CLI PR #33 verification: 369 backend tests, Ruff checks and compatibility 17/17 passed.
For frontend changes run `pnpm lint`, `pnpm typecheck`, `pnpm format:check`, `pnpm build`.
Frontend foundation: lint, strict production build and format check passed; locally served
Inter Latin is 48.25 kB. No backend code changed. GitHub CI also checks frontend formatting.
Research workspace: 8 Playwright Chromium scenarios passed against the production build,
including exact quote/source matching, aliases/errors, combined filters, cutoff/empty states,
sources/history/keyboard navigation, mobile overflow and failed-chunk reload recovery.
Run `pnpm exec playwright install chromium` once, then `pnpm test:e2e` (builds before testing).
CI installs Chromium and runs these browser checks after lint/format/build.
Optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE` selects an installed local binary;
`PLAYWRIGHT_SCREENSHOT_DIR` exports preview screenshots outside the repository.
FastAPI TestClient hangs in the sandbox; backend checks that use it require an unsandboxed run.

Next: review/merge #34 and this workspace PR, then connect the approved backend API.
Resolver and full evidence-list endpoints remain needed for an API-driven evidence explorer;
report's `sources` contains only cited evidence, so it must not silently replace the full list.
Report and trace UI remain Dasha's scope; their navigation entries are noninteractive placeholders.
Integrate live collection after reviewing existing Resolver/connectors. Update this file in every PR.
