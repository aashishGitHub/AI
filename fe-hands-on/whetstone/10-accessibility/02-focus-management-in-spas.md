# Focus management in SPAs: route changes, modals, deletions and skip links
**Round:** 10 · Accessibility · **Level:** Senior · **Time:** 12 min · **Tags:** focus management · spa routing · keyboard
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: after a route change focus stays on the old link; deleting a row dumps focus to the page top; a modal doesn't return focus on close.

## What they're really testing
Do you understand that client-side routing removes the browser's free "new page" behaviour, and can you define a deterministic focus target for every DOM mutation that removes or replaces the focused element?

## Core answer (key points)
- **Why SPAs break:** on a full page load the browser resets focus to the document and the SR announces the new title. With `history.pushState` nothing happens, so focus stays on a link that may not even exist any more.
- **Route change recipe:**
  1. Update `document.title`.
  2. Move focus to the new page's `<h1>` (or `<main>`) made programmatically focusable with `tabIndex={-1}`.
  3. Optionally announce "Navigated to X" via a polite live region (useful when focus target has little text).
  - Skip on initial load (user expects top of page) and on in-page state changes like filters or query params (announce results instead).
- **Modals:** on open, focus the first meaningful element (or the dialog itself), trap Tab inside, make background inert. On close, return focus to the trigger. Native `<dialog>` with `showModal()` gives inert background and Escape; you still verify focus return.
- **Deletions / disappearing elements:** when the focused node is removed, focus falls to `<body>` and keyboard users restart from the top. Move focus to the next item, else previous, else the list's heading / empty-state.
- **Menus / popovers:** Escape closes and returns focus to the trigger.
- **Skip link:** first focusable element, visually hidden until focused, targets `<main id="main" tabindex="-1">`.
- **Visible focus:** never `outline: none` without a replacement; use `:focus-visible` and keep >= 3:1 contrast (WCAG 2.2 added focus-appearance criteria; I'm not certain of every numbering detail, verify 2.4.11 vs 2.4.13 in the spec).

## Mental model / flow
```
Event that changes what's on screen
  ├─ route change ........ title → focus h1(tabindex -1) → (announce)
  ├─ dialog open ......... save trigger → focus inside → trap/inert
  ├─ dialog close ........ restore saved trigger
  ├─ focused node removed  next sibling ?? prev sibling ?? section heading
  └─ in-page update ...... DON'T move focus → live-region announce
```

## Code sketch
```tsx
function usePageFocus(title: string) {
  const ref = useRef<HTMLHeadingElement>(null);
  const { pathname } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    document.title = `${title} | App`;
    if (first.current) { first.current = false; return; }
    ref.current?.focus();
  }, [pathname, title]);
  return ref; // <h1 ref={ref} tabIndex={-1}>
}

function focusNeighbour(rows: HTMLElement[], removedIdx: number, fallback: HTMLElement) {
  (rows[removedIdx] ?? rows[removedIdx - 1] ?? fallback).focus();
}
```

## Trade-offs & pitfalls
- Focusing `<main>` vs `<h1>`: heading reads a short, meaningful name; main can read a lot or nothing depending on SR.
- `tabIndex={-1}` elements get a focus ring on programmatic focus in some browsers; style `:focus:not(:focus-visible)` deliberately rather than removing outlines globally.
- Router libraries differ: some (Gatsby/Reach historically) handled focus for you; Next/React Router largely leave it to you. Verify the current version's behaviour.
- Returning focus to a trigger that was itself unmounted (e.g. inside the deleted row) needs a fallback.
- Scroll restoration and focus can fight; `focus({ preventScroll })` helps control it.

## Likely follow-ups
- *Why not just announce, without moving focus?* Then keyboard users' next Tab starts from the stale position in the old page.
- *How do you test?* Unplug the mouse: Tab through each flow; then VoiceOver/NVDA smoke test; automated: assert `document.activeElement` in Testing Library/Playwright.
- *`inert` attribute?* Makes a subtree unfocusable and hidden from AT; good for background behind a custom modal.
- *Multiple skip links?* Fine for complex layouts (skip to search, to results), but keep it short.

## Say it in 60 seconds
A multi-page site gets focus reset and a title announcement for free; an SPA must recreate that. On route change I update `document.title`, move focus to the new `<h1>` with `tabIndex=-1`, and optionally announce politely, but not on first load or on filter changes. For dialogs I save the trigger, move focus in, make the background inert, and restore focus on close. Whenever the focused element is removed, like a deleted row, I pick a deterministic neighbour: next, else previous, else the section heading, so focus never drops to `<body>`. Add a skip link to `<main>` and keep `:focus-visible` rings with enough contrast. I verify with keyboard-only runs, a screen reader pass, and `activeElement` assertions in E2E tests.
