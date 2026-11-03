# 09 · Testing & Quality
> A defensible testing strategy, Testing Library done right, MSW network mocking, flaky E2E and CI speed, visual + a11y automation, and async hook tests · 6 questions · ~1 h 22 min
Source: https://whetstone-v1.vercel.app/#testing-quality

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Design a frontend testing strategy for a large product | Lead / Staff | 15 min | testing strategy · testing trophy · unit tests | [notes](01-frontend-testing-strategy-large-product.md) |
| 02 | Testing Library principles: queries, user-event, async utilities, and what not to test | Senior | 15 min | testing library · user-event · queries | [notes](02-testing-library-principles-queries.md) |
| 03 | Mock the network, not the fetch function: MSW across unit tests, Storybook and development | Senior | 12 min | msw · mocking · network | [notes](03-msw-mock-network-not-fetch.md) |
| 04 | Eliminate flaky E2E tests and cut CI time (a war story you can tell) | Lead / Staff | 18 min | e2e · cypress · playwright | [notes](04-eliminate-flaky-e2e-cut-ci.md) |
| 05 | Visual regression and automated accessibility tests: what do they catch and miss? | Senior | 10 min | visual regression · chromatic · axe | [notes](05-visual-regression-automated-a11y.md) |
| 06 | Test custom hooks and async UI: fake timers, races and act() warnings | Senior | 12 min | testing · hooks · fake timers | [notes](06-test-hooks-async-fake-timers.md) |

## How these connect
- **01 is the strategy;** 02, 03 and 06 are how the big integration layer is written well; 04 is how the thin E2E layer stays trustworthy; 05 covers the visual and a11y bands.
- **02 + 03 together:** role-based queries + network-level mocks = tests that survive refactors and fail only on user-visible breakage. Same "test at the boundary" idea.
- **02 + 05 link to round 10 (Accessibility):** "can't find it by role" and axe failures are a11y bugs; know what automation misses.
- **06 pairs with round 03 (Async patterns):** debounce, races and cancellation are the code; this is how to prove them deterministically.
- **04 is the behavioral/war-story answer;** rehearse it in STAR form with your own real numbers.
- **Suggested order:** 01 → 02 → 03 → 06 → 04 → 05.
