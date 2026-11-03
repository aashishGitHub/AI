# Testing Library principles: queries, user-event, async utilities, and what not to test
**Round:** 09 · Testing & Quality · **Level:** Senior · **Time:** 15 min · **Tags:** testing library · user-event · queries
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: one test breaks whenever a class name changes; another passes even though the button can't be reached by keyboard. Rewrite the approach. (Site offers React/Angular/Vue code; notes use React.)

## What they're really testing
That you query like users and assistive tech, interact realistically, wait correctly, and treat "hard to query by role" as an accessibility signal.

## Core answer (key points)
- **Query priority:** `getByRole(role, { name })` → `getByLabelText` → `getByPlaceholderText` / `getByText` / `getByDisplayValue` → `getByAltText` / `getByTitle` → `getByTestId` (escape hatch for canvas, charts, non-semantic things).
- **Why role first:** it couples tests to the accessible contract, not markup. A class-name refactor can't break it, and a `<div onClick>` "button" won't be found as a button, so the test fails for the same reason a keyboard/screen-reader user is blocked. That fixes both broken tests in the scenario.
- **Variants:** `getBy*` throws if absent (should exist), `queryBy*` returns null (assert absence), `findBy*` returns a promise that retries (async appearance). `*AllBy*` for lists.
- **user-event over fireEvent:** `userEvent.setup()` then `await user.click/type/tab/keyboard`. It fires the realistic sequence (pointer, focus, keydown, input, keyup) and respects disabled/pointer-events; `fireEvent` dispatches one synthetic event. `await user.tab()` lets you assert keyboard reachability.
- **Async:** prefer `await screen.findByRole(...)` for appearance; `waitFor` only for assertions that become true later, with no side effects inside (it re-runs). Never `setTimeout` sleeps.
- **act() warnings** mean a state update happened after the test stopped waiting. Fix by awaiting the UI change that causes it, not by wrapping things in `act` blindly.
- **Don't test:** internal state names, which hook/function was called, CSS classes (unless the class *is* the contract), third-party internals, giant snapshots.

## Mental model / flow
```
user intent ─► find element by role+name ─► user-event interaction ─► await visible outcome
                     │ not found?
                     └─► likely a11y bug (missing role, label, or name) — fix the component
```

## Code sketch
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';

test('saves a contact and clears the form', async () => {
  const user = userEvent.setup();
  server.use(http.post('/api/contacts', () => HttpResponse.json({ id: 'c1', name: 'Ada' }, { status: 201 })));

  render(<ContactForm />, { wrapper: AppProviders });

  await user.type(screen.getByRole('textbox', { name: /name/i }), 'Ada');
  await user.click(screen.getByRole('button', { name: /save/i }));

  expect(await screen.findByRole('status')).toHaveTextContent(/saved/i);
  expect(screen.getByRole('textbox', { name: /name/i })).toHaveValue('');
});

test('save button is reachable by keyboard', async () => {
  const user = userEvent.setup();
  render(<ContactForm />, { wrapper: AppProviders });
  await user.tab(); // name field
  await user.tab(); // save
  expect(screen.getByRole('button', { name: /save/i })).toHaveFocus();
});
```

## Trade-offs & pitfalls
- `getByRole` is slower on large trees (computes accessibility tree); usually fine, but scope with `within(container)` in huge DOMs.
- jsdom's accessibility/role computation isn't identical to browsers; for complex widgets also verify in a real browser.
- Overusing `data-testid` reintroduces implementation coupling and hides a11y gaps.
- `waitFor` with a long timeout masks slow code; investigate instead.
- Asserting intermediate loading states makes tests timing-sensitive unless the spinner is a requirement.
- Using `container.querySelector` bypasses the whole philosophy; lint it (eslint-plugin-testing-library).

## Likely follow-ups
- **When is `getByTestId` acceptable?** Non-semantic regions (canvas, chart internals) or disambiguating identical items when role+name can't.
- **How do you name things for `getByRole`?** Accessible name comes from content, `aria-label`, `aria-labelledby`, or `<label>`; tests reveal when it's missing.
- **`screen` vs destructured queries?** `screen` is bound to `document.body`, works for portals, less boilerplate.
- **How do you test a modal?** `getByRole('dialog', { name })`, assert focus moved inside, Escape closes, focus returns to trigger.
- **Should you use snapshots?** Only small, intentional ones (serialized data); not big component trees.

## Say it in 60 seconds
I query the DOM the way users and assistive tech do: getByRole with an accessible name first, then labels and text, and test ids only as a last resort for non-semantic things like canvas. That means a class-name refactor can't break the test, and a div pretending to be a button simply isn't found, so the test fails exactly when a keyboard or screen-reader user would. I interact with user-event, which produces the realistic focus, key and pointer sequence, and I can tab through to check keyboard reachability. I wait with findBy for things that appear and waitFor only for later assertions, never sleeps. An act warning means something updated after I stopped waiting, so I await the visible result instead of silencing it. And I don't assert on internal state, hook calls, CSS classes or big snapshots.
