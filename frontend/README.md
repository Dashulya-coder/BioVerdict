# BioVerdict frontend

React 19 + Vite 8 + strict TypeScript. Shared styles use Tailwind CSS 4 with its
[official Vite plugin](https://tailwindcss.com/docs/installation/using-vite).
The approved dark console and component contracts are in
[the design system](../docs/design-system.md).

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
