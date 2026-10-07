# BioVerdict design system

Approved direction (2026-10-07): **dark analytical console**, English interface.
[Canva concept](https://canva.link/oup7kd6ugksa668) establishes the layout and palette;
the implementation corrects its overlapping text and adapts it to small screens.
The source of truth for tokens is `frontend/src/index.css`, shared by both tracks.

## Colors

| Token / Tailwind suffix | Value | Use |
|---|---|---|
| `canvas` | `#111714` | Main background |
| `sidebar` | `#0D1310` | Navigation and inset form fields |
| `surface` | `#19211C` | Panels and subtle controls |
| `raised` | `#202B24` | Hovered surfaces |
| `selected` | `#24372D` | Selected rows and navigation |
| `ink` | `#E7EDE6` | Main text |
| `muted` | `#A4B0A6` | Secondary text and metadata |
| `rule` | `#303C33` | Decorative dividers and panel borders |
| `accent` | `#80CDBB` | Primary actions, focus, source provenance labels |
| `assumption` | `#D3B47A` | Explicit assumptions and review prompts |
| `danger` | `#E89A92` | Failures and invalid input |

Use semantic utilities: `bg-canvas`, `text-ink`, `border-rule`, `text-assumption`.
Avoid new raw colors in feature components. Green is an interaction/provenance accent,
not a positive investment verdict. A quoted source fact is not a claim of clinical efficacy.
Pair every status color with text; absence of evidence must not look like a reassuring result.

## Type, spacing and layout

- Inter Variable, served locally; system sans-serif fallback. Monospace only for IDs,
  timestamps and compact metadata. Do not load fonts from a third-party CDN.
- Body: 14px, 20–28px line height. Metadata: 12px. Page headings: 30–36px, medium weight.
  Source quotations: 14px with at least 24px line height. Preserve their original wording.
- Use the Tailwind 4px spacing scale. Field gaps 8px; related groups 16px; panel padding
  24px; page padding 24px on mobile and 40px on desktop. Corners are 4px or 6px.
- Desktop: persistent sidebar, thin top bar, generous central work area. Evidence uses
  a table and inspector. On mobile, navigation wraps and the inspector stacks below the list.
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
