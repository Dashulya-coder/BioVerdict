# ADR-008: Toolchain versions and pinning policy

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

The project runs on a hard demo date. In October 2026 several runtimes were in transition: Python 3.15 was scheduled for final release on 2026-10-01, Node.js 26 enters LTS on 2026-10-28 and the Node release model changes, and TypeScript 7 (a native Go compiler) is new and lacks a stable programmatic API until 7.1. Version numbers found online came from snapshots of different ages.

## Decision

- Python 3.14.x (newest patch) with `uv`. Verified: the full backend dependency set installs and passes `scripts/check_compat.py` (17 of 17 checks) on CPython 3.14.4. Fallback order if a needed package fails: 3.13, then 3.12; never 3.11 or lower; Node 24 LTS; React 19.3, Vite 8, TypeScript 7 for the build.
- FastAPI, Pydantic v2 (at least 2.12 for Python 3.14 wheels), LangGraph 1.2.x.
- Pin through lock files (`uv.lock`, `package-lock.json`), `.python-version` and `engines`. Record the resolved versions in `docs/stack.md` on day 1.
- No dependency upgrades after the code freeze except through a PR that re-runs tests and the eval set.

## Options Considered

| Dimension | A: newest everything (Python 3.15, Node 26) | B: newest stable with mature ecosystem (chosen) | C: older (Python 3.11-3.12, Node 22) |
|---|---|---|---|
| Wheel/ecosystem risk | higher | low | lowest |
| Language/tool features | newest | recent | older |
| Support horizon | longest | long | Node 22 maintenance ends 2027-04-30 |
| Surprise risk before demo | higher | low | low |

## Trade-off Analysis

B gives current libraries and tooling with a low risk that a package lacks wheels or an API changed. A can be revisited after the hackathon. C is safe but misses what we were asked to use ("newest versions") without a technical reason.

## Consequences

- Easier: reproducible installs on two laptops and the demo machine.
- Harder: type-aware linting may need TypeScript 6 alongside TypeScript 7 until 7.1.
- Heavy ML libraries (vector databases, local embeddings, ONNX runtimes) were capped below 3.14 in downstream projects we saw; we do not use them. New dependencies require a passing `check_compat.py`.
- SDK majors have moved (anthropic 1.x, openai 3.x, google-genai 2.x); all provider calls stay inside `llm.call`.
- Revisit Python 3.15 and Node 26 after the demo.

## Action Items

1. [ ] Create the skeleton, run `uv sync` and `npm install`, run `scripts/check_compat.py` on both machines, run the tests.
2. [ ] Fill in the "Resolved versions" table in `docs/stack.md`.
3. [ ] Set the freeze date in `CONTRIBUTING.md`.
