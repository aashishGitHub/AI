# The rules of ARIA: semantic HTML first, roles, states, properties and accessible names
**Round:** 10 · Accessibility · **Level:** Senior · **Time:** 12 min · **Tags:** aria · semantic html · accessible name
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: a custom dropdown built from `div role="button"` with `aria-label` sprinkled everywhere announces badly. Review it.

## What they're really testing
Do you know ARIA only changes the accessibility tree (what AT is told), never behaviour, and do you reach for native elements before ARIA?

## Core answer (key points)
- **ARIA is metadata, not behaviour.** A `role` changes what the screen reader announces. It adds no focusability, no Enter/Space handling, no state toggling. Putting a role on an element is a promise that you will build all of that yourself.
- **The five rules (W3C "Using ARIA"), my paraphrase:**
  1. Use a native element or attribute if one exists.
  2. Don't override native semantics (wrap a `<button>` inside the `<h2>`, don't make the `<h2>` a button).
  3. Every interactive ARIA control must work from the keyboard.
  4. Never hide a focusable element from AT (`aria-hidden="true"` or `role="presentation"` on something you can Tab to).
  5. Every interactive element needs an accessible name.
- **Roles / states / properties:** role = what it is (`button`, `listbox`, `tab`). State = changes often (`aria-expanded`, `aria-checked`, `aria-selected`, `aria-pressed`, `aria-invalid`). Property = fairly static relationship or description (`aria-controls`, `aria-describedby`, `aria-labelledby`).
- **Accessible name computation (rough order):** `aria-labelledby` → `aria-label` → native labelling (`<label>`, `alt`, `<legend>`, `<caption>`) → subtree text content (for roles that allow name-from-content) → `title` as a last resort. Note: I am not certain the exact precedence between some fallbacks; the spec is "Accessible Name and Description Computation" (accname), verify edge cases there.
- **Review of the dropdown:** replace the div trigger with `<button aria-expanded aria-controls>`. If it's a pick-one control with no typing, a native `<select>` may be enough. If it needs filtering, it's a combobox pattern (APG), which is where ARIA is genuinely needed. Remove blanket `aria-label`s that override visible text.
- **No ARIA beats bad ARIA:** a wrong role (e.g. `role="menu"` for site navigation) makes SR users expect arrow-key menu behaviour that isn't there.

## Mental model / flow
```
DOM ──► browser builds Accessibility Tree ──► platform a11y API ──► screen reader
         ▲ native element = role + name + state + keyboard
         ▲ ARIA attrs      = override role/name/state ONLY (no keyboard, no focus)
```

## Code sketch
```html
<!-- bad: announced as "button" maybe, but no Tab stop, no Enter/Space -->
<div role="button" aria-label="Choose plan" onclick="toggle()">Plan: Pro ▾</div>

<!-- good: native button, visible text is the name, state exposed -->
<button type="button" aria-expanded="false" aria-controls="plan-list">Plan: Pro</button>
<ul id="plan-list" role="listbox" hidden>…</ul>

<!-- icon-only: name it, hide the decorative svg -->
<button type="button" aria-label="Close"><svg aria-hidden="true" focusable="false">…</svg></button>
```

## Trade-offs & pitfalls
- `aria-label` that differs from visible text breaks voice control ("click Save" fails if name is "Submit form"). WCAG 2.5.3 Label in Name.
- `placeholder` is not a label; it disappears and is often low contrast.
- Repeated "Edit / Edit / Edit" buttons: give each context via visually-hidden text or `aria-labelledby="edit-btn row-42-title"`.
- Links navigate (`<a href>`), buttons perform actions. Mixing them breaks SR rotor lists and middle-click.
- `aria-hidden` on a parent hides all descendants, including focusable ones: classic rule 4 violation.

## Likely follow-ups
- *aria-hidden vs `hidden` vs `display:none`?* `hidden`/`display:none` remove for everyone; `aria-hidden` removes from AT only (still visible); `.sr-only` CSS hides visually only.
- *What does `role="application"` do?* Disables SR browse-mode shortcuts so keystrokes go to the page. Almost never right.
- *`aria-label` vs `aria-labelledby`?* `labelledby` reuses visible text by id (translates, stays in sync); `label` is a hidden string.
- *Does ARIA affect SEO or styling?* Not behaviour; you can style via `[aria-expanded="true"]` selectors, which keeps state and visuals in sync.
- *When is ARIA truly needed?* Composite widgets with no native equivalent: tabs, combobox with filtering, tree, grid, live regions.

## Say it in 60 seconds
ARIA only edits the accessibility tree; it never adds focus or keyboard behaviour. So my first move reviewing that dropdown is to delete ARIA, not add it: the trigger becomes a real `<button>` with `aria-expanded` and `aria-controls`, and if it's a plain choice I'd consider a native `<select>`. ARIA is justified only where HTML has no equivalent, like a filterable combobox, and then the role is a contract: I implement the APG keyboard model and states. Every interactive thing needs an accessible name, ideally from visible text so voice-control users can say it. I'd also strip `aria-label`s that override visible text and make sure nothing focusable sits under `aria-hidden`.
