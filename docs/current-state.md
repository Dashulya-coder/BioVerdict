# Current project state

Last inspected: 2026-10-07, main checkout at `100a96e`.
This is a handoff snapshot, not a substitute for inspecting the current branch.
Update it after a task changes capabilities, checks or next steps.

## Working now

- SQLite evidence store, migrations, HTTP cache, stable IDs, `as_of` filtering,
  latest-status selection and hashed/versioned frozen bundles.
- ClinicalTrials.gov connector, sponsor extraction, raw fixtures and divarasib bundle.
- LLM client: schema validation, cache, retries, failover, budgets/deadlines,
  circuit breaker, call log, fake provider and Anthropic adapter.
- Mechanism/translation reasoner, quote grounding, explicit unknowns,
  deterministic confidence, PoS and verdict gates.
- FastAPI `/health`; React/Vite starter with a working counter.

## Not implemented on this branch

- Full resolver and pipeline wiring; underwriting CLI (`run`, `doctor`, `warm`, `eval`).
  Console entry point currently prints a greeting.
- Report/evidence/diff API, SSE, full report UI and UI/API integration.
- Release verifier/entailment judge, incremental report recompute,
  commercial/rNPV/capital model, complete evaluation runner.
- OpenAI/Gemini provider adapters and additional planned source connectors.

Other worktrees have separate A5 changes. They are not merged into this checkout;
check `git worktree list` and review their branches before rebuilding the same work.

## Verified baseline

- `make check`: passed; Ruff check, Ruff format (82 files), pytest **303 passed**,
  frontend ESLint and TypeScript/Vite production build.
  The same checks also passed in each prepared Codex and Claude worktree.
- No live LLM requests were used for this baseline.
- `make compat`: **17/17** offline compatibility checks passed.
- `make browser-check`: **1 passed**, Chromium rendered the starter, the counter
  responded and no uncaught page errors were observed. This is a harness check,
  not a full underwriting/report integration test.
- Codex doctor outside sandbox: **21 ok, 0 warn, 0 fail**; Claude doctor found
  no installation issues. All three project skills passed the skill validator;
  JSON/TOML config and shared links are valid. A new session is needed to load them.
- Local GitHub CLI, Codex and Claude are authenticated. GitHub keyring checks
  require access outside this session's sandbox; an in-sandbox failure was misleading.

## Current task and next step

AI workflow setup is complete: root Makefile checks, this handoff snapshot,
task template, shared settings, browser harness and three shared project skills.
Dedicated Codex and Claude worktrees are at `/tmp/bioverdict-ai/codex` and
`/tmp/bioverdict-ai/claude`, based on `100a96e`, with separate installed dependencies.
AI setup files are uncommitted copies; unrelated user edits and secrets were not copied.
See `CONTRIBUTING.md` for launch commands, task briefs and maintenance.

Latest product work is recorded below. The user requested stopping after A4 and
the approved frontend restyle; do not start another implementation automatically.

## Known limitations

- Documentation includes intended commands and stale unchecked work-plan rows.
- Grounding downgrades unsupported extracted claims to `inferred`; the planned
  release verifier must enforce the stricter failed-claim rule in CONTRIBUTING.
- No complete live underwriting flow exists on main; offline unit tests do not
  establish live-provider correctness or end-to-end report delivery.

## Latest product handoff — checked 2026-10-07

The baseline above describes the local main checkout at `100a96e`. GitHub PRs
were rechecked for this update. Completed feature code lives in separate worktrees;
open PRs must not be reported as merged main functionality.

| PR | State | Delivered scope | Local worktree / dependency |
| --- | --- | --- | --- |
| [#31](https://github.com/Dashulya-coder/BioVerdict/pull/31) | Open | Fixture API/pipeline: reports, drill-down, trace, SSE | `arsenii/A5-api-fixture` |
| [#33](https://github.com/Dashulya-coder/BioVerdict/pull/33) | Open | Offline CLI and JSON export | `/tmp/bioverdict-cli-worktree`; depends on #31/#14 |
| [#34](https://github.com/Dashulya-coder/BioVerdict/pull/34) | Open | Tailwind 4, semantic tokens, local Inter, strict TS and shared UI primitives | `/tmp/bioverdict-design-worktree` |
| [#35](https://github.com/Dashulya-coder/BioVerdict/pull/35) | Open | Input → resolved assumptions → evidence/sources demo | `/tmp/bioverdict-frontend-worktree`; depends on #34 |
| [#36](https://github.com/Dashulya-coder/BioVerdict/pull/36) | Open | Bounded grounded fixture collection → frozen bundle | `/tmp/bioverdict-collect-worktree`; independent of frontend/API/CLI PRs |
| [#38](https://github.com/Dashulya-coder/BioVerdict/pull/38) | Open | Approved warm dark editorial frontend | `/tmp/bioverdict-editorial-worktree`; depends on #35 |

### CLI and A4

#33 implements `bioverdict run --asset divarasib [--as-of YYYY-MM-DD] [--db PATH]
[--fixtures PATH] [--output PATH]`, also via `python -m bioverdict`. It reuses the
fixture API pipeline, emits JSON on stdout and optional report export, and rejects
live mode. Only Divarasib has a complete prepared run. `doctor`, `warm` and `eval`
remain planned. CLI branch verification: 369 backend tests and compatibility 17/17.

#36 introduces injected-tool collection, grounded quote/value extraction, explicit
section statuses, cutoff/latest-wins selection, provenance preservation and an
async collect → freeze graph. Defaults cap each section at 8 tool steps, 90 seconds,
50 records and 24,000 source characters; extraction schema caps 32 facts per call.
Invalid quotes/values/IDs are rejected; truncation/partial failures remain explicit.
No shared evidence schema, deterministic scores or financial outputs were changed.
Its offline example is `scripts/collect_fixture.py`; 29 new tests, 332 backend tests,
Ruff and compatibility 17/17 passed. Live connectors/Resolver registration and
API/CLI/full graph lifecycle wiring remain. Cancelling an async wait cannot kill a
blocking provider worker; live adapters still require their own timeouts.

### Frontend, design and launch

#35 provides prepared Divarasib aliases (Divarasib, GDC-6036, RG-6330), resolved
fixture values and explicit assumptions, source/type/search filters, full original
quotes, source links, clipboard copy, cutoff/empty/error states and keyboard/history
navigation. It lazily loads Zod-validated fixture data. It does not call the backend,
run models, verify the bundle hash or reconstruct historical source revisions.
Cutoffs cannot exceed 2026-10-07. Report/trace entries remain placeholders.

The user selected #38's dark editorial design, superseding the earlier dark
console and both light concepts. Reference: https://canva.link/92wk5z92z6lv5ez.
Palette: canvas `#171C18`, sidebar `#111611`, surface `#20271F`, raised `#273024`,
selected `#2D382C`, ink `#E8E3D7`, muted `#AFB3A5`, rule `#394435`, control `#74806B`,
accent `#AEC2A1`, assumption `#C3A777`, danger `#E89A92`. Lora is local for headings
and wordmark; Inter remains the control/body/quote font. Evidence has a compact
ID/date/source/type table beside a reading pane, stacking on mobile. Use plain
backgrounds and actual fixture copy, not Canva photography or invented navigation.
Both owners use [the shared design system](https://github.com/Dashulya-coder/BioVerdict/blob/arsenii/A5-dark-editorial/docs/design-system.md).

Run the latest UI from its existing worktree (dependencies are installed):

```sh
cd /tmp/bioverdict-editorial-worktree/frontend
pnpm dev
```

Open the URL printed by Vite, normally http://localhost:5173. Check
**Open analysis → Explore evidence → Sources**, then search/filter/copy a quotation.
No backend, API key or paid service is required. For a fresh checkout, first run
`pnpm install --frozen-lockfile`. `/tmp` worktrees/previews may be cleaned by the OS;
the implementation is preserved in the pushed branches.

#38 code commit: `2f59201`. Lint, strict TypeScript/build, Prettier and 8 production
Chromium scenarios passed; both GitHub CI jobs passed on that commit. Local Lora
adds a 37.78 kB Latin WOFF2 asset. Palette checks: 21 text pairs >=5.32:1 and control
boundaries >=3.29:1 on their backgrounds; not a complete accessibility audit.
Screenshots: `/tmp/bioverdict-editorial-preview/{input-desktop,resolved-desktop,evidence-desktop,evidence-mobile}.png`.

### New teammate change and remaining work

[#37](https://github.com/Dashulya-coder/BioVerdict/pull/37) is merged on GitHub
(`da55825`), but not in this local main or the existing feature worktrees.
It adds `DropKind` and `Drop.is_citation_failure`; links/basis count as citation
failures, duplicate links/type overrides do not. The PR reports 306 passing tests.
Required follow-up for #31/#33: use the new property instead of parsing `Drop.what`,
and count only citation failures in the dropped-claim event. Do not implement that
follow-up as part of a context-only update.

Other pending work: #14 hash fix, #28 Open Targets, #30 Resolver part 1 (based on
#28), #32 CT results/pagination/stopped studies and PubMed. Merge frontend in order
#34 → #35 → #38. API integration needs Resolver and full evidence-list endpoints;
report sources contain cited evidence only. Live collection/reasoning integration,
independent entailment verification, financial modules, recompute/diff and eval
remain. Dasha owns report/trace and remaining reasoning/financial modules.

The updated work plan in #36/#38 records whole-task counts, not effort percentages:
Arsenii 0 complete / 7 partial (A1–A6, A11) / 5 remaining (A7–A10, A12);
Dasha 3 complete (B1, B2, B4) / 3 partial (B8, B10, B11) / 7 remaining.
Local main's older work-plan rows have not yet received those unmerged updates.

## Update — 2026-10-08

Everything above this line predates the sync and is partly stale: PRs #14–#44 are all merged and
local `main` is now at `1beb74d`. Local `AGENTS.md` was kept as an uncommitted change on request;
the other pre-sync local edits are in `git stash` ("local-pre-sync-2026-10-08") and in
`../BioVerdict-local-backup-2026-10-08/`.

[#45](https://github.com/Dashulya-coder/BioVerdict/pull/45) (open, branch
`arsenii/A4-live-pipeline`): live runs with `USE_FIXTURES=0` through the API and the CLI
(`pipeline/live_run.py`, `live_sources.py`, `live_llm.py`, shared `reason_score.py`), and a fix
for the date-pinned Open Targets tests that made `main` red from 2026-10-08.

Checks on the branch: Ruff check/format, pytest 604 passed, compatibility 17/17. Manual runs
against real Open Targets, ClinicalTrials.gov and PubMed with a stand-in model worked for
divarasib, sonelokimab and HRO761. No run with a real model has been made: cost, time and
extraction/reasoning quality are unmeasured.

Known problems: `.env.example` still says the live pipeline is not wired in (the file is
read-protected for the agent); `RUN_TIMEOUT_S=420` may be short for a full live run; the A4
per-source caps mark large registry sections `incomplete`.

Next: a paid live run by the user, then UI → API wiring, A7 fallback diff, A8 eval/pre-warm.

[#46](https://github.com/Dashulya-coder/BioVerdict/pull/46) (open, branch `arsenii/A5-ui-api`,
stacked on #45): `GET /runs/{id}/resolver`, `GET /runs/{id}/evidence`, `mode` in `/health`; the
workspace runs on the API with `pnpm dev:api` or `VITE_API_URL` and stays an offline snapshot
without them. Checks: backend pytest 609 passed; frontend lint, format, build and Playwright 14
passed (8 snapshot + 6 API-mode with a test-answered API); manual check against a real fixture
backend. Not checked on a live run with a real model. Next: A7 fallback diff, A8 eval/pre-warm.

[#47](https://github.com/Dashulya-coder/BioVerdict/pull/47) (open, branch
`arsenii/A7-recompute-diff`, stacked on #46): `POST /runs/{id}/evidence` recomputes as a new run
on the next bundle version (full re-run fallback, no schema change), `GET /runs/{id}/diff`
compares two finished runs in code, and the UI has a Compare screen in API mode. Checks: pytest
633 passed, Playwright 17 passed, manual check against a real fixture backend. A recompute with a
real model has not been run. Next: A8 eval runner and cache pre-warm.

[#49](https://github.com/Dashulya-coder/BioVerdict/pull/49) (open, branch `arsenii/A8-eval-warm`,
stacked on #47): `bioverdict eval` (cases, repeats, code-counted grounding/coverage/stability/cost
metrics, JSON + Markdown report), `bioverdict warm` (retrieval cache and readiness table),
grounding drops written to `verification_log`, PyYAML declared. Checks: pytest 664 passed, compat
17/17; eval on the fixture case and warm for divarasib on real sources. Not run live with a model.
This file and `project-review-recommendations.md` were committed by mistake in #47; both branches
now untrack them (copies also in `../BioVerdict-local-backup-2026-10-08/docs/`).
Open problem: target-class registry search returns far more than the 50-record collection cap.

[#50](https://github.com/Dashulya-coder/BioVerdict/pull/50) (open, branch
`arsenii/A4-collect-priority`, stacked on #49): collection reads findings and the newest records
first; the target-class search keeps status and design of up to 12 stopped and 12 other studies;
`warm` paces itself (1 request/s, 5 attempts); the resolver handles a gene listed on X and Y
(CRLF2). pytest 670 passed. `warm` ran over the organizers' 20 assets (local, ignored:
`data/assets_all.tsv`, `data/warm.md`, `data/warm.json`): all read without problems. Not confirmed
in Open Targets: amycretin, elironrasib, zoldonrasib, mivelsiran (searched by name only). No
disease id for the wordings "multiple sclerosis", "pancreatic cancer" (ambiguous; "pancreatic
ductal adenocarcinoma" resolves) and "MSI-high solid tumors" ("colorectal cancer" resolves).
The user has decided against paid model runs for now.
