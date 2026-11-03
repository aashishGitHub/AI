# 10 · Accessibility
> Semantics-first ARIA, SPA focus handling, composite-widget keyboard models, live announcements, forms, and scaling a11y across an org · 6 questions · ~1 h 13 min
Source: https://whetstone-v1.vercel.app/#accessibility

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | The rules of ARIA: semantic HTML first, roles, states, properties and accessible names | Senior | 12 min | aria · semantic html · accessible name | [notes](01-rules-of-aria-semantic-html.md) |
| 02 | Focus management in SPAs: route changes, modals, deletions and skip links | Senior | 12 min | focus management · spa routing · keyboard | [notes](02-focus-management-in-spas.md) |
| 03 | Keyboard interaction patterns: roving tabindex vs aria-activedescendant | Lead / Staff | 15 min | keyboard navigation · roving tabindex · aria-activedescendant | [notes](03-roving-tabindex-vs-activedescendant.md) |
| 04 | Announcing dynamic changes: live regions, status messages and accessible toasts | Senior | 10 min | aria-live · status messages · toasts | [notes](04-live-regions-and-toasts.md) |
| 05 | Accessible forms: labels, descriptions, error summaries and validation timing | Senior | 12 min | forms · labels · validation | [notes](05-accessible-forms-and-validation.md) |
| 06 | Make accessibility stick across 50 engineers: design system, linting, CI and audits | Principal | 12 min | accessibility program · design systems · governance | [notes](06-accessibility-program-at-scale.md) |

## How these connect
- 01 is the foundation: every later answer assumes "native element first, ARIA is a contract you must fulfil".
- 02 and 03 are both about *where DOM focus lives*: 02 at page/flow level, 03 inside a single widget. Study them together.
- 04 covers the case where focus should *not* move, so announce instead. It is the counterpart to 02.
- 05 is the applied exam: it combines names (01), focus after submit (02) and announcements (04) in one form.
- 06 is the org-level version: how the design system bakes 01-05 into primitives so product teams cannot get them wrong.
- Suggested order: 01 → 02 → 03 → 04 → 05 → 06.
