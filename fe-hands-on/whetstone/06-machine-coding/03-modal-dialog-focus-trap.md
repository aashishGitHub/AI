# Build a modal dialog: focus trap, scroll lock, stacking, and why <dialog> helps
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 30 min · **Tags:** modal · dialog · focus management
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
An accessible modal (title, body, actions) that handles nested modals and long content, and judgment on what native `<dialog>` gives you vs what you still own.

Tests: open → focus on first focusable; close → focus back on trigger; Tab wraps last→first, Shift+Tab first→last; Escape closes only the top modal of two; body can't scroll and background isn't tabbable while open.

## Core answer (key points)
- **Modal contract:** focus moves in on open; focus is trapped; Escape (and optionally backdrop click) closes; background is inert to keyboard and AT; background scroll locked; focus restored to the opener; accessible name (`aria-labelledby` → title).
- **`<dialog>` + `showModal()` gives:** top-layer rendering (no z-index wars, no portal needed), `::backdrop`, background made inert, initial focus handling, Escape fires `cancel` → `close`. Nested `showModal()` stacks correctly; Escape closes the topmost.
- **You still own:** syncing React `open` prop with the imperative API, scroll lock, focus restore (browsers vary; do it explicitly), backdrop-click detection (`event.target === dialog`), close animations, initial focus choice.
- **Without `<dialog>`:** portal to `body`, `role="dialog" aria-modal="true"`, set `inert` on app root, manual Tab trap, modal stack so only the top handles Escape and focus returns down the stack.
- **Initial focus rules:** first field for forms; least destructive button for confirmations; the dialog/heading itself (`tabIndex=-1`) for long read-only content.

## Mental model / flow
```
open=true  → save activeElement → dialog.showModal() → focus initial → lock scroll
Esc        → 'cancel' event → (preventDefault if blocking) → close → 'close' event → onClose()
backdrop   → click target === <dialog> → onClose()
open=false → dialog.close() → unlock scroll → restore focus to saved element
stack:     [modalA, modalB]  Esc → B only → focus returns to element inside A
```

## Code sketch
```tsx
export function Modal({ open, onClose, title, initialFocus, children }: {
  open: boolean; onClose: () => void; title: string;
  initialFocus?: RefObject<HTMLElement | null>; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d || !open) return;
    const opener = document.activeElement as HTMLElement | null;
    d.showModal();
    (initialFocus?.current ?? d.querySelector<HTMLElement>('[autofocus],button,input,select,textarea,a[href]'))?.focus();
    const release = lockScroll();
    return () => {
      if (d.open) d.close();
      release();
      opener?.focus?.();
    };
  }, [open, initialFocus]);

  return (
    <dialog ref={ref} aria-labelledby={titleId} className="modal"
      onClose={onClose}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal__panel">
        <h2 id={titleId}>{title}</h2>
        {children}
        <button type="button" className="modal__x" aria-label="Close" onClick={onClose}>×</button>
      </div>
    </dialog>
  );
}

let locks = 0;
function lockScroll() {
  const root = document.documentElement;
  if (locks++ === 0) {
    root.style.setProperty('scrollbar-gutter', 'stable');
    root.style.overflow = 'hidden';
  }
  return () => { if (--locks === 0) { root.style.overflow = ''; root.style.removeProperty('scrollbar-gutter'); } };
}

// Manual trap, only for the non-<dialog> fallback
function onTrapKeyDown(e: KeyboardEvent, box: HTMLElement) {
  if (e.key !== 'Tab') return;
  const f = [...box.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])')]
    .filter(el => el.getClientRects().length > 0);
  if (!f.length) return e.preventDefault();
  const [first, last] = [f[0], f[f.length - 1]];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
```
(The panel wrapper is needed so clicks inside padding don't count as backdrop clicks: the `<dialog>` element itself receives backdrop clicks.)

## Trade-offs & pitfalls
- `onClose` from `<dialog>` fires for any close (Esc, `close()`); make the parent's `open` state the source of truth to avoid double-close loops.
- iOS Safari: `overflow:hidden` on `html` may not stop rubber-band scroll; libraries use `position: fixed` + saved scroll offset.
- Scrollbar disappearance shifts layout; `scrollbar-gutter: stable` or padding compensation.
- Exit animations on `<dialog>` need `@starting-style` and `transition-behavior: allow-discrete` (newer CSS; check support) or a delayed close.
- Escape on a form-in-progress: intercept `cancel` and confirm discard.
- Ref-counted scroll lock matters for nested modals.

## Likely follow-ups
- **`inert` vs `aria-hidden`?** `inert` removes from tab order *and* AT and blocks clicks; `aria-hidden` only hides from AT.
- **Non-modal dialog?** `dialog.show()`: no inert, no trap; also consider the `popover` attribute for light-dismiss UI.
- **Testing?** Testing Library + `user.tab()`; jsdom's `<dialog>` support has been partial (`showModal` may need a polyfill/stub) — verify for your jsdom version, or test in Playwright.
- **Drawer / sheet?** Same contract, different CSS.

## Say it in 60 seconds
A modal has a fixed contract: move focus in, trap it, close on Escape and optionally backdrop click, make the background inert, lock background scroll, restore focus to the opener, and label it by its title. I build on native `<dialog>` with `showModal()` because it gives me the top layer, the backdrop, an inert background, Escape handling and correct stacking for nested modals. My component syncs the `open` prop to `showModal`/`close` in an effect, saves and restores the previously focused element, picks a sensible initial focus, ref-counts a scroll lock, and treats a click whose target is the dialog itself as a backdrop click. Without `<dialog>`, I'd add a portal, `aria-modal`, `inert` on the app root and a manual Tab trap with a modal stack.
