# Eliminate flaky E2E tests and cut CI time (a war story you can tell)
**Round:** 09 · Testing & Quality · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** e2e · cypress · playwright
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: E2E suite takes 60 min and fails randomly ~15% of runs; engineers re-run until green. You have a quarter. Tell it as an interview story.

## What they're really testing
A STAR story with engineering depth: measured first, fixed by root cause, sped up with the right levers, quantified result, and a mechanism to prevent backsliding.

## Core answer (key points)
- **Measure first:** per-spec duration and failure/retry rate from CI artifacts (JUnit reports, Playwright/Cypress dashboards). Usually a small set of specs causes most flakes and most minutes.
- **Root causes of flakiness:**
  - Timing assumptions (fixed sleeps, racing the UI).
  - Shared state (tests depending on data/order from other tests, shared staging env).
  - Non-determinism (clock, randomness, animations, third-party widgets).
  - Infrastructure (oversubscribed runners, slow env).
- **Fixes by cause:**
  - Sleeps → web-first auto-retrying assertions (`await expect(locator).toBeVisible()`), wait on specific network responses.
  - Order dependence → each test seeds its own data via API and cleans up; run in random order locally.
  - Shared env → ephemeral preview environments or unique tenant/user per run.
  - Third parties → block/stub with `page.route` / `cy.intercept`.
  - Animations → disable in test mode, emulate reduced motion.
  - Time → fixed clock (`page.clock`, `cy.clock`).
  - Brittle selectors → role/label locators, `data-testid` for the rest.
  - Retries → allow one, but report retried passes as flaky and track them.
- **Speed levers:** shard across runners balanced by historical duration (not file count); affected-only on PRs, full on main/nightly; log in once via API and reuse storage state; seed via API not UI; push validation/edge cases down to component tests; cache installs, builds, browser binaries; smoke specs first; cancel superseded runs.
- **Result + guard:** e.g. 60 → ~20 min, flake rate down sharply, merge throughput up. Guard with a flake dashboard, auto-quarantine with an owner and SLA (fix or delete), and a CI duration budget.

## Mental model / flow
```
Measure ─► Classify (timing | state | nondeterminism | infra) ─► Fix by cause
   │                                                                   │
   └──────────────── Speed: shard + affected + API setup + push down ◄─┘
                                   │
                  Guard: flake metric, quarantine SLA, duration budget
```
STAR skeleton: **S** 60 min, ~15% random failures, re-run culture → **T** make CI trustworthy and fast in a quarter → **A** measure, fix causes, shard, push down → **R** numbers + what you'd do next.

## Code sketch
```ts
// playwright.config.ts (excerpt)
export default defineConfig({
  retries: process.env.CI ? 1 : 0,
  fullyParallel: true,
  use: { trace: 'on-first-retry', storageState: 'playwright/.auth/user.json' },
  projects: [{ name: 'setup', testMatch: /auth\.setup\.ts/ }, { name: 'e2e', dependencies: ['setup'] }],
});

// test: own data, role locators, auto-retrying assertion, stubbed third party, fixed clock
test('closes an invoice', async ({ page, request }) => {
  await page.route('**/widget.chatvendor.example/**', (r) => r.abort());
  await page.clock.setFixedTime(new Date('2026-01-15T10:00:00Z'));
  const inv = await (await request.post('/api/test/invoices', { data: { ref: `e2e-${test.info().testId}` } })).json();

  await page.goto(`/invoices/${inv.id}`);
  await page.getByRole('button', { name: 'Close invoice' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByRole('status')).toHaveText(/closed/i);
});
```
Shard in CI: `npx playwright test --shard=1/4` … `4/4` across a matrix (balance by duration with a reporter or a timing-aware splitter).

## Trade-offs & pitfalls
- Retries without tracking just hide flakes; worse, they hide real race bugs in the product.
- Test-only seeding endpoints must be disabled in production (feature flag/env guard) — security risk otherwise.
- Ephemeral environments cost money and spin-up time; balance with tenant isolation on a shared env.
- Affected-only runs can miss cross-cutting changes (shared config, design tokens); always run full suite on main.
- Pushing tests down requires trust in component tests; show escaped-defect data to justify deleting E2Es.
- Don't invent numbers in the interview; use your own real metrics or say "roughly".

## Likely follow-ups
- **How did you decide which E2Es to delete?** Mapped each to a user journey; kept critical ones, moved edge cases to component tests, deleted duplicates.
- **What's a quarantine policy?** Auto-tag flaky specs (e.g., failed then passed on retry N times), run them non-blocking, ticket to owner, fix or delete within ~2 weeks.
- **Cypress vs Playwright?** Playwright: multi-browser incl. WebKit, multiple tabs/origins, parallel by default, auto-wait locators. Cypress: great DX, in-browser runner, historically single-tab and same-origin constraints (relaxed with `cy.origin`).
- **How do you balance shards?** Record per-spec duration and bin-pack; file-count splitting leaves one shard with all the slow specs.
- **How do you know it stayed fixed?** Dashboards of flake rate and p95 duration per week, alert on regression.

## Say it in 60 seconds
Our E2E suite took about an hour and failed randomly around one run in six, so people re-ran it and stopped trusting it. I started by measuring per-spec duration and failure rate from CI reports, which showed a handful of specs caused most of the flakes and most of the time. The causes were fixed waits, tests sharing data and environments, third-party widgets, animations and real clocks. We replaced sleeps with auto-retrying assertions and waits on specific responses, seeded data per test through the API, stubbed third parties, froze the clock and disabled animations. Then we sharded by historical duration, reused a logged-in storage state, ran only affected specs on PRs and moved validation cases into component tests. CI dropped to around twenty minutes, re-runs mostly disappeared, and we kept it there with a flake dashboard and a quarantine-with-owner policy.
