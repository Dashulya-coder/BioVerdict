# BioVerdict: context for coding agents

Read this file, `CONTRIBUTING.md`, and the relevant documents in `docs/` before editing.
Read `docs/handoff.md` first: it holds open notes from one person to the other. If a note there
is addressed to your user, tell them what it says before you start on anything else.
Documentation describes the intended product; inspect the code and the open pull requests before
claiming that a feature is implemented or missing.

## Working agreement

- Create a separate branch for each feature, following `arsenii/<task-id>-<short-name>` or
  `dasha/<task-id>-<short-name>`. Use Conventional Commits and open a PR against `main` after
  testing and pushing. Review previous commits for local conventions. Do not merge without authorization.
- Record progress in `docs/work-plan.md` (task status) and in the documents of what you changed.
  Keep this file for rules that stay true. Do not put branch, PR or test-count status in it:
  every PR would then edit the same lines and conflict with every other PR.
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
contracts, and scoring. `docs/work-plan.md` tracks owners, status and milestones;
`docs/runbook.md` contains operating commands (including the `bioverdict` CLI and the run API);
`docs/limitations.md` lists what the system cannot know. Runtime: Python >=3.14, Node 24; use
the existing lockfiles.

## Frontend

Tailwind CSS 4 through the Vite plugin, semantic colour tokens, a self-hosted Inter, shared typed
primitives, strict TypeScript, type-aware ESLint and Prettier with Tailwind class sorting. The
approved direction is the dark analytical console with an English UI. `docs/design-system.md` is
the shared contract between both tracks: use Tailwind and small decomposed components for new UI.
Each person works in their own `frontend/src/features/` folder (the report and trace screens are
Dasha's; the shell, routes and API client are Arsenii's).

## Verification

From `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.
From the repository root: `uv run --project backend python scripts/check_compat.py` (17 checks).
From `frontend/`: `pnpm lint`, `pnpm typecheck`, `pnpm format:check`, `pnpm build`.
GitHub CI runs the same checks. FastAPI's `TestClient` can hang inside a filesystem sandbox, so
backend tests that use it may need an unsandboxed run.
