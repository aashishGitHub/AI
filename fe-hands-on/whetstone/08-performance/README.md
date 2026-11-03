# 08 · Performance
> Core Web Vitals in depth, INP fixes, bundle strategy, images and fonts, a profiling method, CI budgets and perceived speed · 7 questions · ~1 h 44 min
Source: https://whetstone-v1.vercel.app/#performance

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Diagnose and fix LCP, INP and CLS on a real page | Senior | 20 min | core web vitals · lcp · inp | [notes](01-diagnose-fix-lcp-inp-cls.md) |
| 02 | INP deep dive: long tasks, input delay, yielding, and React-specific fixes | Lead / Staff | 18 min | inp · long tasks · scheduler.yield | [notes](02-inp-deep-dive-yielding-react.md) |
| 03 | Bundle strategy: code-splitting boundaries, vendor chunks, tree-shaking failures and budgets | Lead / Staff | 15 min | bundling · code splitting · tree shaking | [notes](03-bundle-strategy-splitting-budgets.md) |
| 04 | Images and fonts: responsive images, formats, lazy loading, font-display and layout shift | Senior | 12 min | images · fonts · avif | [notes](04-images-fonts-layout-shift.md) |
| 05 | A repeatable React profiling workflow | Senior | 15 min | profiling · react devtools · performance panel | [notes](05-react-profiling-workflow.md) |
| 06 | Lab vs field data, RUM, and enforcing performance budgets in CI | Lead / Staff | 12 min | rum · lighthouse ci · performance budgets | [notes](06-lab-vs-field-rum-budgets-ci.md) |
| 07 | Perceived performance: skeletons, optimistic UI, prefetching on intent and view transitions | Senior | 12 min | perceived performance · skeletons · optimistic ui | [notes](07-perceived-performance-techniques.md) |

## How these connect
- **01 is the hub.** It decomposes each vital; 04 is the deep fix for LCP/CLS (images, fonts), 02 is the deep fix for INP. Study 01 → 04 → 02.
- **Method questions (05, 06):** 05 is the local debugging loop for one interaction; 06 is the org-wide measure-and-enforce loop. Same idea at two scales: measure, attribute, fix, guard.
- **Bytes vs main thread:** 03 (bundle) reduces download + parse cost, which feeds both LCP render delay and INP input delay during hydration.
- **07 is the UX layer** on top: once real speed is reasonable, perceived speed wins the "feels instant" comparison.
- **Pair with round 07:** 07-01 (rendering path), 07-04 (resource hints) and 07-07 (workers) are the browser mechanics behind these answers.
- **Suggested order:** 01 → 04 → 02 → 05 → 03 → 06 → 07.
