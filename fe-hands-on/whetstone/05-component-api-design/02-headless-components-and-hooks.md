# Headless components and hooks: separating behavior from rendering
**Round:** 05 · Component API Design · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** headless ui · hooks · prop getters
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
Platform thinking: three design systems duplicate dropdown logic. Can you define the behavior/rendering split, design a `useCombobox` API any team can render, and be honest about costs?

## Core answer (key points)
- **Headless = behavior without markup/styles.** The hook owns state, keyboard model, ARIA wiring, focus management, ids; the consumer owns elements, styles, layout, animation.
- **API shapes:**
  - **Prop getters** (`getInputProps()`, `getItemProps({ item, index })`) — most flexible; they *merge* consumer props instead of clobbering. Downshift popularized this.
  - **Render props** — `<Combobox>{state => ...}</Combobox>`; fine but nests awkwardly.
  - **Compound parts** — `<Combobox.Input/>`; better when structure matters (portals, focus scope).
- **Prop getters must compose:** call consumer `onClick` first, respect `event.defaultPrevented`, merge `className`, compose `ref`s.
- **Layering in a design system:** behaviors package (headless, a11y-tested) → styled UI package (tokens) → product code. Product drops to behaviors only for genuinely custom UI.
- **Buy before build:** React Aria, Radix Primitives, Ark UI, Downshift, TanStack Table already encode years of a11y edge cases. Wrap one rather than writing a combobox from scratch.
- **Test once:** behavior tests run against the hook with a minimal reference renderer; each design system only tests visuals.

## Mental model / flow
```
useCombobox({ items, itemToString, onSelect, value?/defaultValue? })
  state: inputValue, isOpen, highlightedIndex, selectedItem
  returns:
    getLabelProps()  → htmlFor
    getInputProps()  → role=combobox, aria-expanded, aria-controls,
                       aria-activedescendant, onKeyDown(↑↓ Enter Esc), onChange
    getMenuProps()   → role=listbox, id
    getItemProps(i)  → role=option, id, aria-selected, onMouseMove, onClick
consumer: any elements, any styles, spreads getters
```

## Code sketch
```tsx
function callAll<E extends { defaultPrevented: boolean }>(...fns: (((e: E) => void) | undefined)[]) {
  return (e: E) => { for (const fn of fns) { if (e.defaultPrevented) return; fn?.(e); } };
}

export function useCombobox<T>({ items, itemToString, onSelect }: {
  items: T[]; itemToString: (t: T) => string; onSelect?: (t: T) => void;
}) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(-1);
  const [input, setInput] = useState('');
  const id = useId();
  const optId = (i: number) => `${id}-opt-${i}`;

  const choose = (i: number) => {
    const item = items[i];
    if (!item) return;
    setInput(itemToString(item)); setOpen(false); onSelect?.(item);
  };

  return {
    isOpen: open, highlightedIndex: hi, inputValue: input,
    getInputProps: (p: ComponentProps<'input'> = {}) => ({
      ...p,
      role: 'combobox', 'aria-expanded': open, 'aria-controls': `${id}-list`,
      'aria-autocomplete': 'list' as const,
      'aria-activedescendant': open && hi >= 0 ? optId(hi) : undefined,
      value: input,
      onChange: callAll(p.onChange, e => { setInput(e.currentTarget.value); setOpen(true); setHi(0); }),
      onKeyDown: callAll(p.onKeyDown, e => {
        if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setHi(h => Math.min(h + 1, items.length - 1)); }
        if (e.key === 'ArrowUp')   { e.preventDefault(); setHi(h => Math.max(h - 1, 0)); }
        if (e.key === 'Enter' && open) { e.preventDefault(); choose(hi); }
        if (e.key === 'Escape') setOpen(false);
      }),
    }),
    getMenuProps: (p: ComponentProps<'ul'> = {}) => ({ ...p, role: 'listbox', id: `${id}-list` }),
    getItemProps: (i: number, p: ComponentProps<'li'> = {}) => ({
      ...p, role: 'option', id: optId(i), 'aria-selected': i === hi,
      onMouseMove: callAll(p.onMouseMove, () => setHi(i)),
      onMouseDown: callAll(p.onMouseDown, e => e.preventDefault()), // keep focus in input
      onClick: callAll(p.onClick, () => choose(i)),
    }),
  };
}
```
(A production version also needs controllable state, ref composition, scroll-into-view, IME composition handling, and empty/loading states.)

## Trade-offs & pitfalls
- Easy to misuse: forget to spread a getter and a11y silently breaks. Mitigate with dev warnings (e.g., check the input received the getter's id) and tests.
- Hooks can't own DOM structure; portals, focus traps and positioning push you toward compound components.
- Upgrade friction: every consumer's markup depends on the getter contract; semver carefully.
- Leaky abstraction: consumers end up needing internal state (`highlightedIndex`) → expose a state reducer / controlled props.

## Likely follow-ups
- **State reducer pattern?** Let consumers intercept transitions (`stateReducer(state, action)`) to customize behavior without forking.
- **How do you prove a11y?** Keyboard tests by role + axe + manual screen reader pass (VoiceOver/NVDA) once per behavior.
- **Why `aria-activedescendant` vs roving focus here?** Focus must stay in the input while typing; the active option is announced via the attribute.
- **When not headless?** Small teams, one visual style: a styled component is faster to adopt.

## Say it in 60 seconds
A headless component owns behavior and accessibility — state, keyboard model, ARIA attributes, focus and ids — and hands rendering entirely to the consumer, usually via a hook that returns state plus prop getters like `getInputProps` and `getItemProps`. Getters matter because they merge the consumer's handlers, classes and refs instead of overwriting them. With three design systems, I'd build one behaviors layer, ideally wrapping React Aria or similar rather than writing a combobox from scratch, test it once, and let each design system ship a styled layer on top. The costs are more work for consumers, easy-to-miss spreads that break a11y, and upgrade friction, so I add dev-time warnings and keep the styled layer as the default path.
