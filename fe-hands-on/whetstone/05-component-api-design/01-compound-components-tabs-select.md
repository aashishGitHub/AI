# Design a compound component API (Tabs, Select) with context, and know when not to
**Round:** 05 · Component API Design · **Level:** Senior · **Time:** 15 min · **Tags:** compound components · context · component api
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
Company-wide `Tabs` with `Tabs.List / Tabs.Trigger / Tabs.Panel`: controlled + uncontrolled, accessible (APG tabs pattern), robust to consumers wrapping parts in their own components, and the judgment to say when this pattern is overkill.

Behavior tests from the prompt: click shows panel and sets `aria-selected`/`aria-controls`; arrows move focus (roving tabindex), Home/End jump; a Trigger outside `Tabs` throws a helpful error.

## Core answer (key points)
- **Design from the call site first.** Write the JSX consumers will type, then build to it.
- **Shared state via private context**, not `React.Children.map`/`cloneElement`. Context survives arbitrary wrapping (a Trigger inside a Tooltip inside a div); child-cloning breaks the moment someone wraps.
- **Root owns state** through `useControllableState` (`value`/`defaultValue`/`onValueChange`).
- **Ids** from `useId()` link `tab ↔ tabpanel` (`aria-controls`, `aria-labelledby`), SSR-safe.
- **Keyboard on the list:** Left/Right (or Up/Down if vertical), Home/End, wrap-around; **roving tabindex** (selected tab `tabIndex=0`, others `-1`) so the list is one Tab stop.
- **Activation mode:** automatic (focus selects) vs manual (Enter/Space selects). Manual when panels are expensive.
- **Guard hook:** `useTabsContext('Tabs.Trigger')` throws `"<Tabs.Trigger> must be used inside <Tabs>"`.
- **Mount strategy:** unmount inactive panels (cheap, loses state) vs keep mounted with `hidden` (keeps state, costs memory) → `keepMounted` prop.
- **Finding triggers:** DOM query on `[role=tab]` inside the list is simple and handles conditional rendering; registration (descendants pattern) is needed for typeahead/index-aware features.
- **When not to:** one fixed layout (`<Avatar name size />`), or every consumer would write the same children. Ship `<SimpleTabs items={[...]}/>` as a thin wrapper over the compound API.

## Mental model / flow
```
<Tabs value? defaultValue? onValueChange?>   state + baseId → Context
  <Tabs.List role=tablist onKeyDown>         keyboard → focus next tab → select
    <Tabs.Trigger value=a role=tab>          reads ctx: selected? tabIndex, aria-*
  <Tabs.Panel value=a role=tabpanel>         reads ctx: render or hidden
```

## Code sketch
```tsx
type TabsCtx = { value: string; select: (v: string) => void; id: string; activation: 'auto' | 'manual' };
const Ctx = createContext<TabsCtx | null>(null);
const useTabs = (part: string) => {
  const c = useContext(Ctx);
  if (!c) throw new Error(`<${part}> must be rendered inside <Tabs>`);
  return c;
};

function Root(props: { value?: string; defaultValue?: string; onValueChange?: (v: string) => void;
                       activation?: 'auto' | 'manual'; children: ReactNode }) {
  const [value, select] = useControllableState({
    value: props.value, defaultValue: props.defaultValue ?? '', onChange: props.onValueChange,
  });
  const id = useId();
  const ctx = useMemo(() => ({ value, select, id, activation: props.activation ?? 'auto' }),
                      [value, select, id, props.activation]);
  return <Ctx.Provider value={ctx}>{props.children}</Ctx.Provider>;
}

function List({ children, ...rest }: ComponentProps<'div'> & { 'aria-label': string }) {
  const { activation } = useTabs('Tabs.List');
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const tabs = [...e.currentTarget.querySelectorAll<HTMLElement>('[role=tab]:not([disabled])')];
    const i = tabs.indexOf(document.activeElement as HTMLElement);
    if (i < 0) return;
    const map: Record<string, number> = {
      ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length,
      Home: 0, End: tabs.length - 1,
    };
    if (!(e.key in map)) return;
    e.preventDefault();
    const next = tabs[map[e.key]];
    next.focus();
    if (activation === 'auto') next.click();
  };
  return <div role="tablist" onKeyDown={onKeyDown} {...rest}>{children}</div>;
}

function Trigger({ value, children, ...rest }: { value: string } & ComponentProps<'button'>) {
  const t = useTabs('Tabs.Trigger');
  const on = t.value === value;
  return (
    <button {...rest} type="button" role="tab" id={`${t.id}-t-${value}`}
      aria-selected={on} aria-controls={`${t.id}-p-${value}`} tabIndex={on ? 0 : -1}
      onClick={e => { rest.onClick?.(e); if (!e.defaultPrevented) t.select(value); }}>
      {children}
    </button>
  );
}

function Panel({ value, keepMounted, children }: { value: string; keepMounted?: boolean; children: ReactNode }) {
  const t = useTabs('Tabs.Panel');
  const on = t.value === value;
  if (!on && !keepMounted) return null;
  return <div role="tabpanel" id={`${t.id}-p-${value}`} aria-labelledby={`${t.id}-t-${value}`}
              hidden={!on} tabIndex={0}>{children}</div>;
}

export const Tabs = Object.assign(Root, { List, Trigger, Panel });
```

## Trade-offs & pitfalls
- Implicit coupling: parts only work inside the root; TypeScript can't enforce structure.
- Bigger API surface to document and version.
- Context value churn: memoize when consumers are heavy.
- `value` strings in ids must be id-safe (sanitize or use index-based ids).
- `Object.assign` statics can hurt tree-shaking and RSC (`Tabs.List` across a client boundary); some libraries export named parts instead (`TabsList`). I'm not certain of every bundler's behavior here.
- Panel `tabIndex=0` only when the panel has no focusable content; APG suggests it, but double tab stops annoy.

## Likely follow-ups
- **Why not `cloneElement`?** Breaks with wrappers/fragments, hides data flow, and is discouraged by React docs.
- **Vertical tabs?** `aria-orientation="vertical"`, map Up/Down.
- **Select vs Tabs?** Select adds listbox/popover, typeahead, `aria-activedescendant` or roving focus, portal + positioning: more reason to use a headless primitive (Radix, React Aria).
- **Test it how?** Testing Library by role: `getByRole('tab', { name })`, `user.keyboard('{ArrowRight}')`, assert focus and `aria-selected`; plus an axe check.

## Say it in 60 seconds
I'd design from the call site: `Tabs` with `List`, `Trigger` and `Panel` parts sharing state through a private context, so consumers control markup, put badges in triggers or wrap parts without breaking anything. The root uses a controllable-state hook so it works controlled or uncontrolled, `useId` wires `aria-controls` and `aria-labelledby`, and the list handles arrows, Home and End with a roving tabindex so it's one tab stop. Each part calls a guard hook that throws a clear error outside `Tabs`. Panels unmount by default with a `keepMounted` option. If the layout is fixed or everyone writes the same children, I'd ship a simple `items` prop wrapper instead.
