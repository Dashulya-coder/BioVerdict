# Stack, versions and pinning policy

## Decision summary

| Layer | Choice |
|---|---|
| Python | **3.14.x** (verified below); fallback 3.13, not 3.11 |
| Package and env manager | `uv` |
| API | FastAPI + Uvicorn, Pydantic v2 |
| Orchestration | LangGraph 1.2.x, as a DAG runner only |
| LLM SDKs | `anthropic`, `openai`, `google-genai` |
| Storage | SQLite (WAL), standard-library `sqlite3` |
| HTTP client | `httpx` (async) |
| Lint, format, tests | Ruff, pytest, pytest-asyncio |
| Frontend | React 19, Vite 8, TypeScript 6.0 (as installed; see the note under the table below) |
| Node.js | 24 LTS (consider 26 after it enters LTS on 2026-10-28) |

## Versions resolved from the registries on 2026-10-06

These were **not** copied from articles. We installed the full backend dependency set on CPython 3.14.4 with `uv`, which resolved the newest releases from PyPI, and queried npm for the frontend packages. They are a floor for your own lock files; run the same commands and record what *you* resolve (table at the bottom).

| Package | Resolved version | Registry |
|---|---|---|
| fastapi | 0.142.2 | PyPI |
| starlette (via FastAPI) | 1.7.0 | PyPI |
| uvicorn | 0.54.0 | PyPI |
| pydantic / pydantic-core | 2.13.5 / 2.46.5 | PyPI |
| httpx | 0.28.1 | PyPI |
| tenacity | 9.1.4 | PyPI |
| numpy | 2.5.3 | PyPI |
| langgraph | 1.2.13 | PyPI |
| langgraph-checkpoint / langgraph-prebuilt | 4.2.0 / 1.1.0 | PyPI |
| langchain-core (pulled in by langgraph) | 1.6.6 | PyPI |
| anthropic (SDK) | 1.11.0 | PyPI |
| openai (SDK) | 3.24.0 | PyPI |
| google-genai (SDK) | 2.28.0 | PyPI |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | PyPI |
| ruff | 0.16.10 | PyPI |
| uv | 0.12.23 | PyPI |
| SQLite (bundled with the Python build) | 3.50.4 | |
| react / react-dom | 19.3.0 | npm |
| vite | 8.3.2 | npm |
| @vitejs/plugin-react | 6.1.2 | npm |
| typescript | 7.0.2 | npm |
| vitest | 5.0.3 | npm |
| tailwindcss | 4.3.3 | npm |
| @xyflow/react | 12.12.0 | npm |
| recharts | 3.10.1 | npm |
| @tanstack/react-query | 5.104.1 | npm |
| eslint | 10.12.0 | npm |

**What the frontend uses (`frontend/package.json`, 2026-10-11).** The table is what the registry
offered on 2026-10-06, not what was installed. The frontend asks for `react` and `react-dom`
`^19.2.8` (the lockfile holds 19.3.0) and `typescript` `~6.0.2` (the lockfile holds 6.0.3), not
TypeScript 7 (see the caveat below on tools that call the compiler). `vitest`,
`@xyflow/react`, `recharts` and `@tanstack/react-query` are not installed; browser tests run on
Playwright.

**SDK major versions have moved** (anthropic 1.x, openai 3.x, google-genai 2.x). Do not copy old code samples. Read each SDK's current documentation, and keep every provider call inside `llm.call` (ADR-004) so only one file changes if an SDK API differs from what you remember.

Runtimes (from release schedules, not from a registry): Python 3.14.8 or newer patch; Node 24.19.0 LTS (2026-08-03; leaves Active LTS on 2026-10-20, supported to 2028-04-30); Node 26.7.0 enters LTS on 2026-10-28. Python 3.15 was scheduled for final release on 2026-10-01; we did not confirm the final release page.

## Does everything work on Python 3.14? Verified result

We ran `scripts/check_compat.py` against a fresh environment on **CPython 3.14.4** with the full dependency set above. **All 17 checks passed**:

- every package imports (fastapi, uvicorn, pydantic, pydantic-core, httpx, tenacity, numpy, langgraph, anthropic, openai, google.genai);
- Pydantic validation and JSON-schema generation work;
- a LangGraph DAG with two parallel nodes compiles and runs;
- SQLite opens in WAL mode;
- a FastAPI app answers through `TestClient`;
- the three SDK clients construct with dummy keys, offline;
- a NumPy Monte Carlo draw runs.

What this does **not** prove: real API calls, behavior on your laptops (Windows or macOS), or packages outside this list. Re-run the script on both machines on day 1.

Supporting evidence from package metadata and project notes: the Anthropic SDK lists Python 3.14 support; google-genai 2.14 lists 3.14; LangGraph needs Python 3.10 or newer and installs on 3.14; Pydantic needs 2.12 or newer for 3.14 wheels.

### Where Python 3.14 can still bite (avoid or verify)

At the time of the sources we saw, some heavier libraries were capped below 3.14 in downstream projects: `chromadb`, `pinecone-text`, `fastembed`, `onnxruntime`, and `arize-phoenix`. Older LangChain 0.x releases were pinned below 3.14, and `langgraph-cli[inmem]` had a build problem that newer releases fixed. We do not need any of these: no vector database, no local embeddings, no LangChain. **Rule: add a new dependency only after running `check_compat.py` with it installed.**

### Why not Python 3.11

- It is in security-only maintenance; Python 3.13 and 3.14 receive bug fixes.
- Nothing in our dependency set needs it: everything above runs on 3.14.
- We would give up current-interpreter improvements for no compatibility gain.

### Fallback rule

If `uv sync` or `check_compat.py` fails on 3.14 for a package we really need: drop to **3.13** (the most widely supported modern release), then 3.12. Do not go below 3.12. Change `.python-version` and `requires-python`, re-lock, re-run the check, and log it in ADR-008.

## Why not Python 3.15 yet

New interpreter releases lag the ecosystem (binary wheels, tooling). `uv` did not index 3.15 pre-releases as recently as September. With a hard demo date, a mature interpreter lowers risk. Revisit after the demo.

## Other notes

**Node 24 now, maybe 26 later.** Choose one runtime, pin it in `.nvmrc` and `engines`. From October 2026 Node moves to one major release a year with every release becoming LTS (starting with Node 27).

**TypeScript 7 caveat (the frontend is on 6.0.x).** `tsc` is now a native Go binary. It does not yet expose a stable programmatic API (planned for 7.1, stable release planned 2026-11-24), so tools that call the compiler (type-aware `typescript-eslint` rules, `ts-morph`, `typedoc`) may need TypeScript 6.0.x beside it. Plan: TypeScript 7 for `tsc --noEmit` and the build; if type-aware lint rules fail, turn them off or keep TypeScript 6.0.x as a separate dev dependency for linting only.

**LangGraph.** Version 1.2 adds per-node timeouts and node-level error handlers; use them for the agent contract's `timeout_s` and the `incomplete` section status. We use only the `langgraph` package, not LangChain or `langgraph-cli`.

## Pinning policy

1. Python: `.python-version` containing `3.14`. Record the full patch below.
2. Backend: `pyproject.toml` with lower bounds from the table above and a committed `uv.lock`. Install with `uv sync --frozen` in CI and on demo machines.
3. Frontend: `package.json` with `engines.node`, a committed `pnpm-lock.yaml`, `pnpm install --frozen-lockfile` for installs. pnpm 12.9.1 is used in CI. The `packageManager` field is deliberately not set: pnpm 12 then writes its own per-platform binaries into the lock file, which churns it between machines.
4. Both developers and the demo machine use the same lock files.
5. **No upgrades after the code freeze** (date in `CONTRIBUTING.md`) except through a PR that re-runs tests, `check_compat.py` and the eval set.

## Project skeleton

`backend/pyproject.toml`:

```toml
[project]
name = "bioverdict"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "fastapi>=0.142",
  "uvicorn[standard]>=0.54",
  "pydantic>=2.13",
  "httpx>=0.28",
  "tenacity>=9.1",
  "numpy>=2.5",
  "langgraph>=1.2",
  "anthropic>=1.11",
  "openai>=3.24",
  "google-genai>=2.28",
]

[dependency-groups]
dev = ["pytest>=9", "pytest-asyncio>=1.4", "ruff>=0.16"]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Commands:

```bash
uv python install 3.14
cd backend
uv init --package --python 3.14
uv add fastapi "uvicorn[standard]" pydantic httpx tenacity numpy langgraph anthropic openai google-genai
uv add --dev pytest pytest-asyncio ruff
uv run python ../scripts/check_compat.py        # must print "17/17 checks passed"

cd ../frontend
pnpm create vite . --template react-ts
pnpm add @xyflow/react recharts @tanstack/react-query
```

## Your resolved versions (fill in on day 1)

| Tool | Machine A | Machine B | Date |
|---|---|---|---|
| Python | TODO | TODO | |
| uv | TODO | TODO | |
| fastapi | TODO | TODO | |
| pydantic | TODO | TODO | |
| langgraph | TODO | TODO | |
| anthropic | TODO | TODO | |
| openai | TODO | TODO | |
| google-genai | TODO | TODO | |
| Node.js | TODO | TODO | |
| react | TODO | TODO | |
| vite | TODO | TODO | |
| typescript | TODO | TODO | |
