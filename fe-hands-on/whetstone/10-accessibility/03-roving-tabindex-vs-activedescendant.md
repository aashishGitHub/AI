# Keyboard interaction patterns: roving tabindex vs aria-activedescendant
**Round:** 10 · Accessibility · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** keyboard navigation · roving tabindex · aria-activedescendant
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: implement keyboard support for a 6-button toolbar and a 100-option listbox; pick a technique for each and justify.

## What they're really testing
Do you know the "one Tab stop per composite widget" model, the two ways to track the active item, and which one survives virtualization and text inputs?

## Core answer (key points)
- **Composite widget rule:** toolbar, tabs, menu, listbox, grid, tree = one Tab stop. Arrow keys move inside; Home/End jump; Tab leaves; Shift+Tab back in lands on the last active item.
- **Roving tabindex:** active item `tabIndex=0`, all others `-1`; arrow keys call `.focus()` on the next item. DOM focus physically moves, so the browser scrolls it into view and the SR announces it natively.
- **aria-activedescendant:** DOM focus stays on the container (or an `<input>`), which has `aria-activedescendant="<id of active option>"`. You paint a visual highlight and scroll it into view yourself.
- **Toolbar (6 buttons):** roving tabindex. Few items, all rendered, best SR support, native scroll.
- **Listbox (100 options):** either works if all are rendered; choose activedescendant if it's virtualized (the next item may not exist in the DOM yet to receive focus) or if it's paired with a text input (combobox: typing must keep going to the input).
- **Keys per pattern (APG):** tabs ←/→ (+Home/End); menu ↑/↓, Enter/Space, Escape returns focus, type-ahead; listbox ↑/↓, type-ahead, Shift+arrows multi-select; grid arrows + Ctrl+Home/End, PageUp/Down; tree ↑/↓, → expand, ← collapse/parent.
- **Wrapping:** decide per pattern (menus and toolbars commonly wrap; APG lists it as optional for several). Be consistent across the design system.

## Mental model / flow
```
ROVING TABINDEX                         ARIA-ACTIVEDESCENDANT
[btn0 ti=0][btn1 ti=-1][btn2 ti=-1]     <input aria-activedescendant="opt-42">  ← DOM focus here
   ▲ DOM focus moves on →                 │ points to (by id)
   └ browser scrolls + SR reads item      ▼
                                        <li id="opt-42" aria-selected> ← visual highlight only
                                          you must scrollIntoView
```

## Code sketch
```tsx
function useRoving(count: number, loop = true) {
  const [active, setActive] = useState(0);
  const els = useRef<HTMLElement[]>([]);
  const go = (i: number) => {
    const n = loop ? (i + count) % count : Math.min(count - 1, Math.max(0, i));
    setActive(n);
    els.current[n]?.focus();
  };
  const keyMap: Record<string, (i: number) => number> = {
    ArrowRight: i => i + 1, ArrowLeft: i => i - 1, Home: () => 0, End: () => count - 1,
  };
  const itemProps = (i: number) => ({
    ref: (el: HTMLElement | null) => { if (el) els.current[i] = el; },
    tabIndex: i === active ? 0 : -1,
    onFocus: () => setActive(i),
    onKeyDown: (e: React.KeyboardEvent) => {
      const f = keyMap[e.key]; if (!f) return;
      e.preventDefault(); go(f(i));
    },
  });
  return itemProps;
}
// activedescendant variant: keep `activeId` in state, set it on the input,
// and call document.getElementById(activeId)?.scrollIntoView({ block: 'nearest' }).
```

## Trade-offs & pitfalls
| | Roving tabindex | aria-activedescendant |
|---|---|---|
| DOM focus | moves to item | stays on container/input |
| Scroll into view | automatic | manual |
| Virtualized lists | fragile (target may be unmounted) | works |
| Typing in an input | breaks (focus leaves input) | works |
| SR support | very solid | good, historically some quirks |
- activedescendant ids must reference elements that are in the DOM and owned by (or controlled by) the focused element.
- Forgetting `onFocus → setActive` means clicking an item leaves the wrong Tab stop.
- Don't put `preventDefault` on all keys: you'll swallow Tab and shortcuts.

## Likely follow-ups
- *How do you test it?* Keyboard-only script: Tab in, arrows, Home/End, Tab out, Shift+Tab back; SR check of announcements; unit tests asserting `tabIndex` and `activeElement`.
- *Grids with interactive cells?* Roving at cell level; Enter/F2 to enter cell content, Escape to return to grid nav.
- *Why not make every item Tab-able?* 100 Tab presses to escape a list; violates expected widget model.
- *Type-ahead?* Buffer keystrokes for ~500ms and jump to first match (timeout value is convention, not spec).

## Say it in 60 seconds
Composite widgets are a single Tab stop with arrow keys inside. There are two ways to track the active item. Roving tabindex moves real DOM focus by flipping `tabIndex` between 0 and -1, so scrolling and announcements come free; I'd use it for the six-button toolbar. With `aria-activedescendant`, focus stays on the container or input and an id points at the active option; I paint the highlight and scroll myself. That's the right pick for the 100-option listbox if it's virtualized or sits under a text input, because the next option may not exist in the DOM and typing must stay in the input. Either way I follow the APG key map, handle Home/End, keep Shift+Tab returning to the last active item, and test with keyboard plus a screen reader.
