# Announcing dynamic changes: live regions, status messages and accessible toasts
**Round:** 10 · Accessibility · **Level:** Senior · **Time:** 10 min · **Tags:** aria-live · status messages · toasts
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: toasts, form errors, a "3 results found" count and a chat feed are mostly missed by SR users, and one region double-announces.

## What they're really testing
Do you know how live regions actually fire (mutation of an already-present region), the polite/assertive split, and how to design toasts that don't fail timing and keyboard criteria?

## Core answer (key points)
- **SRs don't watch the DOM.** They only speak changes in nodes marked as live regions, or the element that receives focus.
- **Types:** `aria-live="polite"` / `role="status"` waits for the SR to finish; `aria-live="assertive"` / `role="alert"` interrupts. Use assertive sparingly (blocking errors only).
- **The region must exist first.** Mount an empty region at app start, then change its text. Mounting a new node already containing text is unreliable across SR/browser combos.
- **Global announcer:** one polite + one assertive region in the app shell, exposed via a hook. Clear then set (next frame) so repeated identical messages are re-announced.
- **Double announcements usually come from:** `role="status"` plus a redundant `aria-live` on nested elements, two announcers mounted, re-rendering the whole region (React key change) so the SR sees remove+insert, or focus moving to the same text that was announced.
- **Toasts:** show visually, announce the text via the polite region. Don't move focus. If a toast has an action (Undo), make it reachable (shortcut to toast area, or a persistent alternative), pause auto-dismiss on hover/focus, and allow enough time (WCAG 2.2.1 Timing Adjustable).
- **Result counts:** debounce, then announce "3 results for 'shoes'". Don't announce per keystroke.
- **Chat feed:** `role="log"` (implicitly polite) on the container, announce only new messages, not the whole history.
- **Errors:** inline text near the field (linked via `aria-describedby`) beats a disappearing toast.
- WCAG 4.1.3 Status Messages is the criterion for "status changes must be programmatically determinable without focus".

## Mental model / flow
```
app shell (mounted once)
 ├─ <div role="status" aria-live="polite"  aria-atomic> ""   ◄─ announce(msg)
 └─ <div role="alert"  aria-live="assertive" aria-atomic> "" ◄─ announce(msg,'assertive')
feature code → useAnnounce() → set("") → rAF → set(msg) → SR speaks diff
```

## Code sketch
```tsx
type Urgency = 'polite' | 'assertive';
const Ctx = createContext<(m: string, u?: Urgency) => void>(() => {});

export function Announcer({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState<Record<Urgency, string>>({ polite: '', assertive: '' });
  const announce = useCallback((m: string, u: Urgency = 'polite') => {
    setMsg(s => ({ ...s, [u]: '' }));
    requestAnimationFrame(() => setMsg(s => ({ ...s, [u]: m })));
  }, []);
  return (
    <Ctx.Provider value={announce}>
      {children}
      <div className="sr-only" role="status" aria-atomic="true">{msg.polite}</div>
      <div className="sr-only" role="alert" aria-atomic="true">{msg.assertive}</div>
    </Ctx.Provider>
  );
}
export const useAnnounce = () => useContext(Ctx);
```

## Trade-offs & pitfalls
- `aria-atomic="true"` reads the whole region on change; without it some SRs read only the changed node.
- Too many announcements = noise; users turn the SR verbosity down or miss the important one.
- Visually-hidden (`.sr-only`) regions, not `display:none` (which removes them from the a11y tree).
- Testing: VoiceOver + Safari and NVDA + Firefox/Chrome behave differently; test at least two pairs.
- I'm not certain of the exact clear-then-set timing needed on every SR; some teams use a ~100ms timeout instead of rAF. Verify on your support matrix.

## Likely follow-ups
- *`role="status"` vs `aria-live="polite"`?* Same politeness; `status` adds semantics and implicit `aria-atomic="true"`.
- *Why not focus the toast?* Steals the user's place; only move focus for dialogs that need a decision.
- *`aria-relevant`?* Controls which mutations announce (additions, removals, text); defaults are usually right, and support is uneven.
- *How to unit-test?* Assert text content of the region via Testing Library `getByRole('status')`; real speech still needs manual SR testing.

## Say it in 60 seconds
Screen readers only speak focus changes and mutations inside live regions, so I mount one polite and one assertive region in the app shell at startup and push text into them through an `announce` hook, clearing first so repeated messages fire again. Status updates like "3 results" go polite and debounced; only blocking errors go assertive, and ideally those are inline next to the field anyway. Toasts get announced, not focused; if they carry an action like Undo, I give it a keyboard route, pause dismissal on hover or focus, and allow enough time. A chat feed is `role="log"` announcing only new items. Double announcements usually mean nested live attributes, two announcers, or re-mounting the region, so I keep exactly one region per politeness level.
