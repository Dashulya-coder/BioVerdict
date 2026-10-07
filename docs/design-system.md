# BioVerdict design system

Approved direction (2026-10-07): **dark editorial workspace**, English interface.
[Latest Canva concept](https://canva.link/92wk5z92z6lv5ez) combines the original dark
analytical console with warm editorial typography and sage accents. It supersedes
the earlier dark and light concepts. The implementation uses plain backgrounds,
existing product navigation and locally served fonts; mockup photography and extra
navigation labels are illustrative. Quotes, dates and identifiers come from fixture data.
The source of truth for tokens is `frontend/src/index.css`, shared by both tracks.

## Colors

| Token / Tailwind suffix | Value | Use |
|---|---|---|
| `canvas` | `#171C18` | Main background |
| `sidebar` | `#111611` | Navigation and inset form fields |
| `surface` | `#20271F` | Panels and subtle controls |
| `raised` | `#273024` | Hovered surfaces and source quotations |
| `selected` | `#2D382C` | Selected rows and navigation |
| `ink` | `#E8E3D7` | Warm main text |
| `muted` | `#AFB3A5` | Secondary text and metadata |
| `rule` | `#394435` | Decorative dividers and panel borders |
| `control` | `#74806B` | Input, select and secondary action boundaries |
| `accent` | `#AEC2A1` | Sage primary actions, focus and source labels |
| `assumption` | `#C3A777` | Explicit assumptions and review prompts |
| `danger` | `#E89A92` | Failures and invalid input |

Use semantic utilities: `bg-canvas`, `text-ink`, `border-rule`, `text-assumption`.
Avoid new raw colors in feature components. Green is an interaction/provenance accent,
not a positive investment verdict. A quoted source fact is not a claim of clinical efficacy.
Pair every status color with text; absence of evidence must not look like a reassuring result.

## Type, spacing and layout

- Inter Variable for controls, tables and quotations; Lora Variable (`font-editorial`)
  for the wordmark, page titles and excerpt heading. Both are served locally as Latin
  WOFF2 files with `font-display: swap`; system sans-serif and Georgia are fallbacks.
  Monospace only for IDs, timestamps and compact metadata. No third-party font CDN.
- Body: 14px, 20–28px line height. Metadata: 12px. Page headings: 30–36px, medium weight.
  Source quotations: 14px with at least 24px line height. Preserve their original wording.
- Use the Tailwind 4px spacing scale. Field gaps 8px; related groups 16px; panel padding
  24px; page padding 24px on mobile and 40px on desktop. Corners are 4px or 6px.
- Desktop: persistent sidebar, thin top bar, generous central work area. Evidence uses
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
| `Badge` | `neutral`, `fact`, `assumption`, `error`; always has readable text |
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
