# Make accessibility stick across 50 engineers: design system, linting, CI and audits
**Round:** 10 · Accessibility · **Level:** Principal · **Time:** 12 min · **Tags:** accessibility program · design systems · governance
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: principal engineer, 50 engineers, recurring a11y regressions; leadership wants it to stick, not another one-off audit.

## What they're really testing
Can you design a socio-technical system (prevention, detection, operations, people) instead of a heroic cleanup, and talk metrics and buy-in?

## Core answer (key points)
- **Frame:** regressions recur because the default path is inaccessible. Make the accessible path the easy path, then catch what slips through.
- **Policy:** pick a target (WCAG 2.2 AA), prioritise critical journeys (sign-up, checkout, core workflow), note legal drivers (ADA in the US, Section 508 for federal, European Accessibility Act enforceable from June 2025; verify current status for your markets, this area changes).
- **Design layer:** contrast-checked colour tokens, focus-ring tokens, motion guidelines (`prefers-reduced-motion`), Figma annotation kits for headings, landmarks, focus order, names. Designers specify, not engineers guess.
- **Component layer (biggest lever):** the design system owns ARIA, keyboard and focus for hard widgets (dialog, combobox, menu, tabs, date picker). Build on proven headless libs (React Aria, Radix) rather than from scratch. Each component documents its a11y contract.
- **Automation:** `eslint-plugin-jsx-a11y`, axe in unit/component tests and E2E, Storybook a11y addon, CI fails on *new* violations with a ratchet on existing ones. Be honest: automated tools catch only a subset of issues; the site says 30-50%, I've seen different estimates, so treat it as "a minority".
- **Manual verification:** PR checklist for new UI (keyboard, 200%/400% zoom, SR smoke), expert audits on a cadence, testing with disabled users on key flows.
- **Operations:** a11y bugs triaged with severity and SLAs like any defect, per-team dashboards, a champions network (one per squad).
- **People:** training for designers and PMs too; a11y in definition of done.
- **Metrics:** open issues by severity and age per team; axe violation trend (only down); % of DS components with passing manual audit; key-journey coverage by keyboard/SR scripts.

## Mental model / flow
```
PREVENT                       DETECT                         RESPOND
policy (WCAG 2.2 AA) ─┐       lint (editor/PR) ─┐            triage + severity
design tokens/annot. ─┼─► code ─► unit axe ─────┼─► release ─► SLA per severity
DS primitives (ARIA, ─┘       E2E axe + ratchet │            dashboards per team
 focus, keyboard)             manual checklist ─┘            champions, training
            ▲                                                       │
            └─────────── recurring issue patterns fed back into DS ◄┘
```

## Code sketch
```ts
// Playwright + @axe-core/playwright: fail only on new violations (ratchet via baseline file)
import AxeBuilder from '@axe-core/playwright';
test('checkout has no new a11y violations', async ({ page }) => {
  await page.goto('/checkout');
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag22aa']).analyze();
  const known = new Set(baseline['/checkout']); // ids of accepted, ticketed violations
  expect(violations.filter(v => !known.has(v.id))).toEqual([]);
});
```
(Verify the exact tag names supported by your axe-core version.)

## Trade-offs & pitfalls
- Hard-failing CI on all existing violations on day one blocks everyone and gets the check disabled. Ratchet instead.
- Over-trusting automation: green axe != accessible (focus order, meaningful names, SR flow are manual).
- DS adoption gaps: teams forking or wrapping components lose the a11y contract; track DS coverage.
- A central a11y team as gatekeeper doesn't scale; champions + DS ownership does.
- Overlays/"a11y widgets" sold as one-line fixes are widely criticised by practitioners; don't propose them.

## Likely follow-ups
- *How do you get buy-in?* Risk (legal), reach (disabled, situational, ageing users), quality (accessible components are better engineered); start with DS for leverage and show quick wins.
- *First 90 days?* Baseline audit of top journeys, fix DS primitives, add lint + ratchet CI, start champions, publish dashboard.
- *How do you prioritise a backlog of 400 issues?* Severity × journey criticality × number of users; fix at component level first (one fix, many screens).
- *VPAT/ACR?* Conformance report enterprise buyers ask for; the program produces evidence for it.

## Say it in 60 seconds
Recurring regressions mean the system makes the inaccessible path easy, so I'd fix the system. Set a target, WCAG 2.2 AA, and prioritise the critical journeys. Put the real leverage in the design system: accessible tokens and annotated designs, and components that own ARIA, keyboard and focus for the hard widgets, ideally on React Aria or Radix. Automate what's detectable with lint, axe in component and E2E tests, and CI that fails on new violations while ratcheting old ones down. That's only a minority of issues, so add a PR checklist, periodic expert audits and testing with disabled users. Operate it like any quality metric: severity, SLAs, per-team dashboards, champions. Sell it on legal risk, reach and engineering quality.
