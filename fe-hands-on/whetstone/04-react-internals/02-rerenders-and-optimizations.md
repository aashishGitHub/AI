# When does a component re-render, and which optimizations actually help?
**Round:** 04 · React Rendering & Internals · **Level:** Senior · **Time:** 15 min · **Tags:** react · rerenders · memo
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Do you know the three real triggers, and do you reach for structural fixes before memoization, backed by profiling? Scenario: a 2,000-row table re-renders on every keystroke in a search box above it.

## Core answer (key points)
- **Three triggers:** own state changes, parent re-renders (props are irrelevant unless the child is memoized), or a consumed context value changes. Props changing is not itself a trigger.
- Re-rendering is normal. The problem is renders that are both frequent and expensive.
- **Fix order (cheapest, most durable first):**
  1. **Colocate state** — move the search state into the component that needs it so the table is not under it.
  2. **Lift content up / children as props** — elements created by the grandparent keep identity when the wrapper's state changes.
  3. **Split contexts by volatility** — fast-changing values in their own context; dispatchers in a separate stable context.
  4. **Selector subscriptions** — `useSelector`, Zustand selectors, `useSyncExternalStore`; only components whose slice changed render.
  5. **Targeted `memo` + stable props** — `React.memo` rows with `useCallback` handlers and memoized derived arrays.
  6. **Virtualize** — 2,000 DOM rows is the real cost; render ~30 visible rows.
- **Prove it:** React DevTools Profiler (highlight updates, flamegraph, "why did this render"), plus the browser Performance panel. A 0.1 ms component re-rendering is noise.
- **React Compiler** auto-memoizes compliant code, making most manual `useMemo/useCallback/memo` redundant.

## Mental model / flow
```
keystroke → setQuery in <Page>
  <Page> renders → every child renders (default)
     ├─ <SearchBox>   (needs it)
     └─ <Table 2000>  (does not) ← move state into SearchBox, or
                                   pass Table as children, or memo + stable props
```

## Code sketch
```tsx
// Before: query lives in Page, so Table re-renders per keystroke
// After: filter state colocated with the consumer that needs it
function Page({ rows }: { rows: Row[] }) {
  return <FilterableTable rows={rows} />;
}

function FilterableTable({ rows }: { rows: Row[] }) {
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);
  const visible = useMemo(
    () => rows.filter(r => r.name.toLowerCase().includes(deferred.toLowerCase())),
    [rows, deferred],
  );
  return (
    <>
      <input value={query} onChange={e => setQuery(e.target.value)} aria-label="Search rows" />
      <VirtualRows rows={visible} />
    </>
  );
}

const RowView = memo(function RowView({ row, onPick }: { row: Row; onPick: (id: string) => void }) {
  return <tr onClick={() => onPick(row.id)}><td>{row.name}</td></tr>;
});
```

## Trade-offs & pitfalls
- `memo` is defeated by one unstable prop: inline `style={{}}`, inline arrow, fresh array.
- `useMemo` everywhere costs memory, comparisons and readability, and does nothing for children that aren't memoized.
- Context `value={{ user, setUser }}` is a new object every render → every consumer re-renders.
- Same-value `setState` bails out via `Object.is`, but React may still render that component once before bailing.

## Likely follow-ups
- **Why does a context consumer re-render though the value "didn't change"?** Provider value is a fresh object each render; memoize it or split state and dispatch contexts.
- **Does `memo` compare deeply?** No, shallow `Object.is` per prop; custom comparator is possible but rarely worth it.
- **When is virtualization wrong?** Small lists, print/find-in-page needs, or variable heights you can't measure cheaply; also a11y (row counts via `aria-rowcount`).
- **How does the Compiler change this?** It memoizes values, callbacks and JSX automatically; structural fixes still matter.

## Say it in 60 seconds
A component re-renders when its state changes, when its parent renders, or when a context it reads changes. Props alone don't trigger anything unless the child is memoized. Re-renders aren't bugs; slow, frequent ones are. I fix structure first: move state down to where it's used, pass expensive subtrees as children so their element identity is stable, split contexts by how often they change, and subscribe to store slices with selectors. Only after profiling do I add `memo` with stable props, and for 2,000 rows I'd virtualize. I prove it in the React Profiler. With the React Compiler on, most manual memoization goes away.
