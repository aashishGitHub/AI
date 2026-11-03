# 05 · Component API Design
> Building components other engineers want to use: compound parts, headless hooks, controllable state, forms, boundaries, API review · 6 questions · ~1 h 24 min
Source: https://whetstone-v1.vercel.app/#component-api-design

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Design a compound component API (Tabs, Select) with context, and know when not to | Senior | 15 min | compound components · context · component api | [notes](01-compound-components-tabs-select.md) |
| 02 | Headless components and hooks: separating behavior from rendering | Lead / Staff | 15 min | headless ui · hooks · prop getters | [notes](02-headless-components-and-hooks.md) |
| 03 | Support controlled and uncontrolled usage with one useControllableState hook | Senior | 12 min | controlled components · uncontrolled · hooks | [notes](03-use-controllable-state-hook.md) |
| 04 | Production forms with react-hook-form and zod: validation, async checks, server errors and field arrays | Senior | 18 min | forms · react-hook-form · zod | [notes](04-production-forms-rhf-zod.md) |
| 05 | Where do you place error boundaries and Suspense boundaries in a large app? | Lead / Staff | 12 min | error boundaries · suspense · resilience | [notes](05-error-and-suspense-boundaries.md) |
| 06 | Review a component API: props explosion, boolean flags, slots and composition | Lead / Staff | 12 min | component api · code review · composition | [notes](06-review-component-api-props.md) |

## How these connect
- **Building block first:** 03 (`useControllableState`) is used by 01 and 02; learn it before either.
- **Three API shapes, one decision:** 01 (compound parts) vs 02 (headless hooks + prop getters) vs plain props — 06 is the review lens that decides between them.
- **Composition over configuration** runs through 01, 02 and 06: slots/children instead of flags, unions instead of booleans.
- **Forms and failure:** 04 (field/async/server errors) and 05 (render errors and loading boundaries) are the "what goes wrong" pair; 05 builds on Suspense from round 04 Q04.
- **A11y is part of the API:** roving tabindex (01), `aria-activedescendant` (02), `aria-invalid`/`describedby` (04), required accessible names (06).
- Suggested order: 03 → 01 → 02 → 06 → 04 → 05.
