# Design a frontend testing strategy for a large product
**Round:** 09 · Testing & Quality · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** testing strategy · testing trophy · unit tests
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: you join a product with 200 slow Cypress tests, almost no unit tests, and frequent regressions. Design the strategy and a migration plan.

## What they're really testing
Whether you optimize for confidence per CI-minute and per maintenance-hour, can assign each concern to the right layer, and can run it as an org program (flake policy, ownership, metrics).

## Core answer (key points)
- **Goal:** maximum confidence per minute of CI and per hour of upkeep, not maximum test count or coverage.
- **Shape ("testing trophy"):** widest band is integration/component tests.
  - **Static (always):** TypeScript strict, ESLint (hooks, jsx-a11y), type tests for public APIs. Cheapest bug filter.
  - **Unit (~20-30%):** pure logic with many edge cases: parsers, formatters, reducers, hooks with real logic. Table-driven.
  - **Integration/component (~50-60%):** render a feature with real children, mock only the network (MSW), drive it like a user (Testing Library). Survives refactors.
  - **E2E (~5-10%):** a thin set of critical journeys (login, checkout, core CRUD) against a real deployed stack; deploy smoke.
  - **Visual + a11y:** where regressions are likely (design system, key pages).
  - Percentages are a heuristic, not a rule.
- **Principles:** test behavior not implementation; one reason to fail per test with a clear message; mock at the network boundary; flaky tests are bugs; coverage is a smell detector, not a target.
- **Migration plan for this team:**
  1. Measure: per-spec duration, flake rate, which regressions escaped and which layer would have caught them.
  2. Stabilize: quarantine flaky specs automatically, fix top offenders.
  3. Push down: move validation/edge-case Cypress specs into component tests with MSW; keep ~20-30 journey E2Es.
  4. Add a "test with the fix" rule: every escaped regression gets a test at the lowest layer that would catch it.
  5. Speed: shard, affected-only on PRs, full on main/nightly.
- **Contract with backend:** typed client generated from OpenAPI/GraphQL schema, plus contract tests (Pact) or schema validation of fixtures.

## Mental model / flow
```
            ▲  E2E (few)            critical journeys, real stack, deploy smoke
           ███ Integration (most)   feature + real children + MSW
          ████ Unit (some)          pure logic, table-driven
        ██████ Static (always)      TS strict, ESLint, type tests
        + Visual (Storybook) + a11y (axe) alongside
```
| Concern | Best layer |
|---|---|
| Currency/date formatting edge cases | Unit |
| Form validation + error messages | Component |
| "Save shows toast and updates list" | Integration + MSW |
| Auth redirect, payments, cross-page flows | E2E |
| Design system visuals | Visual regression |
| a11y violations | axe in component tests, Storybook, key-page E2E |
| Backend contract | Generated types + Pact / schema validation |

## Code sketch
```ts
// Table-driven unit test: cheap, many edge cases.
describe('formatMoney', () => {
  it.each([
    [0, 'USD', 'en-US', '$0.00'],
    [1234.5, 'EUR', 'de-DE', '1.234,50 €'],
    [-5, 'USD', 'en-US', '-$5.00'],
  ])('%d %s %s → %s', (amount, currency, locale, expected) => {
    expect(formatMoney(amount, currency, locale)).toBe(expected);
  });
});
```
(Intl output for some locales uses non-breaking spaces; assert with normalization if needed.)

## Trade-offs & pitfalls
- All-E2E suites are slow, flaky, and give poor failure locality; all-unit suites pass while the integration is broken.
- Component tests in jsdom don't run real layout/CSS; layout bugs need visual or browser-mode tests (Vitest browser mode, Playwright component testing).
- Coverage targets get gamed with assertion-free tests; track escaped-defect rate instead.
- Retries hide real flakes; allow one retry but report retried passes as flaky.
- Too much mocking (module mocks) creates tests that pass with broken wiring.

## Likely follow-ups
- **How do you know the strategy works?** Escaped defects per release, CI p50/p95 duration, flake rate, time-to-merge, and which layer caught each bug.
- **Who owns tests?** Product teams own their tests; a platform team owns the harness, runners, flake dashboard and quarantine tooling.
- **How do you keep CI fast at scale?** Affected-graph runs (Nx/Turborepo), sharding by historical duration, caching, ephemeral preview envs for E2E.
- **Pyramid vs trophy?** Same intent; trophy weights integration tests heavier for UI because they give more confidence per test.
- **What about snapshot tests?** Large tree snapshots get rubber-stamped; small inline snapshots of serialized data are fine.

## Say it in 60 seconds
I optimize for confidence per minute of CI and per hour of maintenance. Static checks like strict TypeScript and ESLint catch a class of bugs for free. The bulk of behavior tests should be integration-level component tests: render a real feature with its children, mock only the network with MSW, and drive it the way a user would, because those survive refactors. Unit tests cover pure logic with lots of edge cases. E2E stays thin, a couple of dozen critical journeys against a real stack. Visual and accessibility checks go where regressions are likely. For this team I'd measure flake rate and duration first, quarantine and fix the worst specs, push validation and edge cases down from Cypress into component tests, and require every escaped bug to get a test at the lowest layer that would have caught it. Then I track escaped defects, CI time and flake rate per team.
