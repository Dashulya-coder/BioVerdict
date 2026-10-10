# BioVerdict design system

Direction: **dark analytical workspace**, English interface. The layout and the neutral black
palette below date from 2026-10-11 ([Canva board](https://www.canva.com/d/T-qG6_ucTsY8fFk):
every screen, two other colour options and the screen before); they replace the olive palette
of 2026-10-07. The palette is proposed by Arsenii and awaits both tracks' approval: changing it
is a change of the tokens only. Quotes, dates and identifiers come from run data.
The source of truth for tokens is `frontend/src/index.css`, shared by both tracks.

## Colors

| Token / Tailwind suffix | Value | Use |
|---|---|---|
| `canvas` | `#0A0B0D` | Main background |
| `sidebar` | `#070809` | Navigation and inset form fields |
| `surface` | `#111316` | Panels and subtle controls |
| `raised` | `#181B1F` | Tiles inside a panel, hovered surfaces, source quotations |
| `selected` | `#1D2126` | Selected rows and navigation |
| `ink` | `#EDEFF2` | Main text |
| `muted` | `#98A0AB` | Secondary text and metadata |
| `rule` | `#23272D` | Decorative dividers and panel borders |
| `control` | `#5C6570` | Input, select and secondary action boundaries |
| `accent` | `#B5D3A4` | Sage: primary actions, focus, links to claims and sources |
| `assumption` | `#E0B46A` | Assumptions, modeled numbers, a Conditional verdict, a weak link |
| `danger` | `#F08A80` | Failures, fired gates, weight against, a Do Not Invest verdict |
| `positive` | `#6FD49A` | Weight for, a supported link, an Invest verdict |

Use semantic utilities: `bg-canvas`, `text-ink`, `border-rule`, `text-assumption`.
Avoid new raw colors in feature components. The sage accent is for interaction and provenance;
a favourable result is `positive`, never the accent. A verdict is coloured through
`verdictLook` (`src/app/verdict.ts`) and nowhere else. A quoted source fact is not a claim of
clinical efficacy. Pair every status color with text; absence of evidence must not look like a
reassuring result.

## Type, spacing and layout

- Inter Variable for controls, tables, quotations, section headings and figures; Lora Variable
  (`font-editorial`) for the wordmark, page titles, the verdict and thesis titles. Both are served locally as Latin
  WOFF2 files with `font-display: swap`; system sans-serif and Georgia are fallbacks.
  Monospace only for IDs, timestamps and compact metadata. No third-party font CDN.
- Body: 14px, 20–28px line height. Metadata: 12px. Page headings: 30–36px, medium weight.
  Source quotations: 14px with at least 24px line height. Preserve their original wording.
- Use the Tailwind 4px spacing scale. Field gaps 8px; related groups 16px; panel padding
  24px; page padding 24px on mobile and 40px on desktop. Corners: 6px controls, 8px tiles,
  12px panels, full for badges.
- Section headings are 20px semibold Inter. A number a reader compares uses the `figure`
  utility (semibold, tabular digits). A bordered block uses the `panel` utility.
- Desktop: persistent sidebar with two groups (Analysis, Results), sticky top bar, generous central work area. Evidence uses
  a compact ID/date/source/type table beside a nearly equal-width reading pane.
  Selection has a sage surface and a left rule. Keep the full quotation in the pane.
  On mobile, navigation wraps and the inspector stacks below the list.
- Use rules and subtle surface differences for hierarchy. Keep one primary action per
  screen. Avoid gradients, glow, oversized marketing headings and decorative charts.

## Shared components

Import directly from `frontend/src/ui/`; keep feature behavior out of these primitives.

| Component | Contract |
|---|---|
| `Button` | Native button props; `primary`, `secondary`, `ghost`; defaults to `type="button"` |
| `Field` | Required `id`/`label`, native input props, optional hint or error; links accessible descriptions |
| `Badge` | `neutral`, `fact`, `assumption`, `error`, `positive`; always has readable text |
| `Meter` | A share from 0 to 1 as a bar, in a status colour; decorative, the number is written beside it |
| `Icon` | Small decorative SVGs; accompanying text supplies the accessible name |
| `PageHeading` | Eyebrow, title and description; one page-level `h1` |

```tsx
import { Button } from '../../ui/Button'
import { Badge } from '../../ui/Badge'

<Button variant="secondary">Back to input</Button>
<Badge tone="assumption">Assumption</Badge>
```

Keep quotations verbatim, with source kind, publication date, identifier and original link.
Use “Fixture value” for resolved demo fields and “Assumption” for inferred fields;
do not label an inferred field as an explicit user input. Future report and trace screens
should reuse these tokens and primitives rather than creating their own palette.

## Interaction and quality

Visible keyboard focus; associated field labels; 44px button/input targets; native controls
where possible; headings and landmarks; descriptive link text; reduced motion support.
Empty, loading and failed states explain what happened and give an appropriate next action.
Tables may scroll inside their region; the whole page must not overflow on mobile.
Use `border-control` for interactive control boundaries; `border-rule` is decorative.

TypeScript uses `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`.
ESLint checks types, React hooks and promises. Prettier sorts Tailwind utilities using this
stylesheet. Do not bypass errors with `any`, non-null assertions, or blanket lint disables.
Validate external data at the boundary and derive display state instead of synchronizing copies.
Memoize expensive work only when justified; preserve the existing React Compiler configuration.

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
```

Ownership: Arsenii owns `src/app/`, `src/features/input/` and `src/features/evidence/`; Dasha owns
`src/features/report/` and `src/features/trace/`. Shared style changes go through review.
