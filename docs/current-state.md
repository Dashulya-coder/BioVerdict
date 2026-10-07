# Current project handoff — 2026-10-07

## Branch and delivery

`arsenii/A5-dark-editorial`, based on workspace PR #35 (`e85cc25`). Its PR targets
`main`; merge the foundation #34 and functional workspace #35 first. This branch
contains their frontend changes but not the separate API/CLI/collection branches.
Do not merge automatically. The user requested stopping after this restyle.

## Implemented here

- Approved dark editorial style: warm forest-charcoal, ivory text and sage accents.
  Reference: https://canva.link/92wk5z92z6lv5ez.
- Local Lora Latin variable font for headings/wordmark; Inter for body and controls.
  Tailwind semantic tokens and typed primitives remain the shared styling boundary.
- Compact ID/date/source/type table beside a wider source quotation pane; clear
  selected rows, responsive stacking and stronger interactive control boundaries.
- Existing fixture input, assumptions, search, filters, cutoffs, sources, clipboard
  and navigation remain functional. No production API or paid model calls.
- Both owners use `docs/design-system.md`; `docs/work-plan.md` includes #36's A4
  progress without claiming its backend code is present on this branch.

## Validation

Frontend lint, strict TypeScript production build and Prettier check passed.
Eight Chromium browser scenarios passed against the production build, covering
fixture flow, source/quote integrity, filters, cutoffs, keyboard/history, mobile
overflow and load-error recovery. The first browser launch used an obsolete local
binary path; the suite passed with installed Chromium 1243. No backend code changed.
Screenshots are generated outside Git in `/tmp/bioverdict-editorial-preview`.
Palette checks: 21 semantic text pairs have contrast >=5.32:1; control boundaries
on sidebar/surface/hover backgrounds have contrast >=3.29:1. This is not a complete
accessibility audit. Local Lora adds a 37.78 kB font asset; existing dependencies
retain their locked versions.

## Remaining

Review the pending PRs before API integration. #31/#33 provide fixture API/CLI;
#36 provides grounded bounded collection and collect/freeze nodes. Live Resolver
and connector registration, complete graph lifecycle, independent entailment
verification and recompute/eval remain pending. Dasha owns report/trace UI and the
remaining reasoning/financial modules. Whole-task counts remain in the work plan.
