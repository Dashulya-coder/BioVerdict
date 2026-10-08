# BioVerdict frontend

React 19 + Vite 8 + strict TypeScript. Shared styles use Tailwind CSS 4 with its
[official Vite plugin](https://tailwindcss.com/docs/installation/using-vite).
The approved dark console and component contracts are in
[the design system](../docs/design-system.md).

## Research workspace

Open the prepared Divarasib demo using `Divarasib`, `GDC-6036` or `RG-6330`, review
fixture-resolved fields and explicit assumptions, then explore evidence and grouped sources.
Search IDs, source names or excerpts; combine source/type filters; select an item for its
verbatim quotation, dates and original source link. Keyboard and mobile layouts are supported.

Evidence comes from `../fixtures/bundles/divarasib.json`; the static resolver fixture was
copied from backend PR #31. Runtime schemas live in `src/app/schemas.ts`, and the demo
client/fixture validation loads only when a demo is opened. It makes no external requests.
The latest selectable cutoff is 2026-10-07. Published records use publication date;
undated records use retrieval date. Changing the date filters visible items only: it does
not reconstruct source revisions, rerun reasoning, verify assumptions or validate bundle hashes.

## Running on the API

`pnpm dev:api` (`vite --mode api`) points the workspace at `http://127.0.0.1:8000`;
`VITE_API_URL` selects another address and also enables the API for `pnpm dev` and `pnpm build`.
Without either, the build opens the snapshot above and makes no requests.

`src/app/api-client.ts` starts a run (`POST /runs`), polls its trace for progress, and once the
bundle is frozen reads `GET /runs/{id}/resolver` and `GET /runs/{id}/evidence`. Answers are
validated with the schemas in `src/app/schemas.ts`. The header shows `Fixture run` or `Live run`
(from the API's `/health`) and the run id. Refusals, failed runs and an unreachable API are shown
with the API's own reason. Wording that differs between the two modes lives in `src/app/copy.ts`.

Report and trace screens are remaining work; see [both tracks' status](../docs/work-plan.md).

## Browser checks

```bash
pnpm exec playwright install chromium
pnpm test:e2e
```

Two Playwright projects run against production builds. `snapshot` (eight scenarios) covers the
prepared demo: filters, cutoffs, keyboard/history navigation, exact quote/source provenance,
mobile overflow and failed-load recovery. `api` (six scenarios) covers the `--mode api` build
with the tests answering for the API: progress, fixture/live labelling, refusals, failed runs,
an unreachable API and malformed answers. Both reject unexpected external requests; neither
needs a backend. CI installs the browser and runs these checks automatically.

Optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE` selects an existing Chromium binary;
`PLAYWRIGHT_SCREENSHOT_DIR` exports screenshots to a directory outside the repository.
Analysis state stays in memory: refreshing an evidence/source URL asks you to open a demo again.

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm lint
pnpm format:check
pnpm build
```

`pnpm typecheck` checks TypeScript separately; the production build also checks types.
`pnpm format` formats code and sorts Tailwind classes.

Import primitives directly from `src/ui/`. Reuse semantic tokens from `src/index.css`;
extend them through a reviewed PR. Inter is served locally as a single Latin variable font.
Keep application wiring in `src/app/`, evidence UI in `src/features/evidence/`,
and Dasha's report/trace UI in their own feature folders.
