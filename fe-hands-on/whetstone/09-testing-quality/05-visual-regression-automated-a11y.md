# Visual regression and automated accessibility tests: what do they catch and miss?
**Round:** 09 · Testing & Quality · **Level:** Senior · **Time:** 10 min · **Tags:** visual regression · chromatic · axe
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: leadership wants visual regression and automated a11y checks to "catch everything". Explain the limits and set them up without noise.

## What they're really testing
Calibrated expectations (what automation can and can't find), deterministic visual testing with a review workflow, and the manual a11y testing that still has to happen.

## Core answer (key points)
- **Visual regression:** screenshot components/pages, diff against approved baselines.
  - Catches: CSS/layout regressions, spacing, z-index, theme/dark-mode breakage, RTL, truncation — things no DOM assertion sees.
  - Misses: behavior, logic, anything not in a captured state; can't tell if a change is intended.
  - Mostly at **component level in Storybook** (Chromatic, Playwright screenshots, Loki): one story per state (default, hover/focus, error, empty, long text, RTL, dark). A few page-level snapshots for integration.
  - **Determinism:** bundled fonts, frozen time, fixed data, disabled animations, fixed viewport + device scale factor, same browser/OS image.
  - **Workflow:** diffs reviewed in the PR; baseline updates are deliberate, approved by the owning team (design system diffs by DS owners/designers).
- **Automated a11y (axe-core, eslint-plugin-jsx-a11y, Storybook a11y addon):**
  - Catches: missing accessible names, low contrast, invalid/misused ARIA, missing labels, duplicate ids, landmark/heading structure issues.
  - Coverage: estimates vary widely — roughly a third of WCAG success criteria are fully automatable, while studies by volume of real issues report around half or more. I don't have exact current figures; cite as approximate.
  - Misses: whether focus order makes sense, visible focus quality, keyboard traps in complex widgets, meaningful alt/link text, screen-reader announcement quality, usability of a whole flow.
- **Manual still required:** keyboard-only walkthroughs, screen reader passes (VoiceOver + Safari, NVDA + Firefox/Chrome), 200-400% zoom/reflow, reduced motion, forced colors/high contrast, content quality.
- **CI placement:** lint on every commit; axe in component tests and on key E2E pages (fail on new violations); visual tests on PRs touching UI; manual audit on new complex widgets and before major releases.

## Mental model / flow
```
               catches                           misses
Visual diff    pixels changed in captured states  behavior, uncaptured states, intent
axe / lint     machine-checkable rules            meaning, order, flow usability
Manual/AT      real experience                    slow, doesn't scale → target key flows
```

## Code sketch
```ts
// Component-level a11y (Vitest + jest-axe)
import { axe } from 'jest-axe';
test('menu button has no detectable violations', async () => {
  const { container } = render(<MenuButton label="Account" items={['Profile', 'Sign out']} />);
  expect(await axe(container)).toHaveNoViolations();
});

// Page-level a11y + visual (Playwright)
import AxeBuilder from '@axe-core/playwright';
test('billing page', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.setFixedTime(new Date('2026-01-01T00:00:00Z'));
  await page.goto('/billing?fixture=standard');
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(violations).toEqual([]);
  await expect(page).toHaveScreenshot('billing.png', { maxDiffPixelRatio: 0.001 });
});
```

## Trade-offs & pitfalls
- Page-level screenshots with live data and animations = constant noise → people auto-approve → the gate is dead.
- Thresholds too loose hide real 1-2 px regressions; too tight flag anti-aliasing differences across OS. Run in a fixed container image.
- Hosted services (Chromatic, Percy) cost per snapshot; prune stories and snapshot only meaningful states.
- axe on a component in isolation misses context issues (page heading order, landmarks); also run on pages.
- Failing CI on all existing a11y violations blocks everyone on day one; baseline existing ones, fail on new, burn down.
- Passing axe is not WCAG conformance; never report it as such.

## Likely follow-ups
- **Who approves visual diffs?** Owning team; design-system diffs by DS maintainers, ideally with designer sign-off.
- **How do you handle dynamic content (dates, avatars)?** Fixtures, frozen clock, mask regions in the screenshot.
- **Why test in multiple browsers?** Font rendering and layout engines differ; at least the main one plus WebKit for Safari-heavy audiences.
- **Where do a11y checks run earliest?** In the editor via lint, in Storybook via the a11y addon while building.
- **What would you manually test on a combobox?** Arrow keys, Enter/Escape, `aria-activedescendant`/focus management, announcements of options and result counts.

## Say it in 60 seconds
Neither catches everything. Visual regression screenshots components or pages and diffs them against approved baselines, so it catches CSS and layout breakage that no assertion would, but only for the states you capture, and it can't tell intended from accidental change. I do it mostly per Storybook story, make rendering deterministic with bundled fonts, frozen time, fixture data and no animations, and require deliberate baseline approval by the owning team. Automated accessibility checks with axe and lint catch machine-checkable problems like missing names, contrast and invalid ARIA, which is a meaningful but partial share of issues. They can't judge focus order, meaningful alt text or whether a flow works with a screen reader, so we still do keyboard and screen-reader passes on key flows. In CI I fail on new violations and burn down existing ones.
