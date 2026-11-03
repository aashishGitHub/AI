# Transitions, useDeferredValue and Suspense: what does concurrency mean in React?
**Round:** 04 · React Rendering & Internals · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** concurrent rendering · usetransition · usedeferredvalue
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
That "concurrency" means interruptible, prioritized rendering, not parallelism or faster code. Scenario: filtering 20,000 items per keystroke lags; someone says "just wrap it in startTransition".

## Core answer (key points)
- **Concurrent rendering:** React can prepare a new tree in the background and abandon it if something more urgent arrives. Single-threaded; it yields between fibers.
- **Urgent vs transition:** typing, clicks are urgent. `startTransition(() => setX())` marks an update as interruptible; stale transition renders are discarded.
- **`useTransition`:** use when *you own the setter*. Returns `isPending` for a subtle indicator. If the new UI suspends, React keeps the old UI on screen instead of flashing the Suspense fallback.
- **`useDeferredValue`:** use when you *receive a value* (prop) and don't control the update. Gives a lagging copy; render the expensive part with it. The expensive child must be memoized or it re-renders with the urgent pass anyway.
- **Suspense:** declarative loading boundary for anything that suspends (`lazy`, `use(promise)`, Suspense-enabled data libs). Place at visual regions that can load independently; nested boundaries reveal progressively and enable streaming SSR.
- **Not fixed by concurrency:** genuinely slow renders (still slow, just non-blocking), long tasks outside React (300 ms JSON parse in a handler), effects. Controlled input values must stay urgent.

## Mental model / flow
```
keystroke
  ├─ urgent lane:     input value updates → commit → paint (fast)
  └─ transition lane: render <Results deferred> in ~5ms slices
         shouldYield()? → yield to browser (MessageChannel task)
         new keystroke arrives → discard work, restart with fresh value
         finished → commit
```

## Code sketch
```tsx
function Search({ items }: { items: Item[] }) {
  const [q, setQ] = useState('');
  const dq = useDeferredValue(q);
  const stale = q !== dq;
  return (
    <>
      <input value={q} onChange={e => setQ(e.target.value)} aria-label="Filter" />
      <div aria-busy={stale} style={{ opacity: stale ? 0.6 : 1 }}>
        <Results items={items} query={dq} />
      </div>
    </>
  );
}
const Results = memo(function Results({ items, query }: { items: Item[]; query: string }) {
  const hits = items.filter(i => i.label.includes(query));
  return <ul>{hits.map(h => <li key={h.id}>{h.label}</li>)}</ul>;
});

function Tabs() {
  const [tab, setTab] = useState<'a' | 'b'>('a');
  const [pending, start] = useTransition();
  return (
    <>
      <button aria-busy={pending} onClick={() => start(() => setTab('b'))}>B</button>
      <Suspense fallback={<Skeleton />}>{tab === 'a' ? <A /> : <B />}</Suspense>
    </>
  );
}
```

## Trade-offs & pitfalls
- Wrapping the input's own setter in a transition makes typing lag.
- `useDeferredValue` without `memo` on the heavy child gives no benefit.
- Too many Suspense boundaries = popcorn UI; too few = one spinner for the page.
- Measure with the Profiler and INP; concurrency often hides cost rather than removing it, so virtualization may still be needed.

## Likely follow-ups
- **Debounce vs `useDeferredValue`?** Debounce waits a fixed time (good for network). Deferred renders ASAP but interruptibly (good for CPU-bound render). Combine them.
- **How does React interrupt?** Work loop checks `shouldYield()` between fibers (roughly 5 ms slices, approximate) and reschedules via a MessageChannel macrotask.
- **What gets thrown away?** The in-progress work-in-progress tree; nothing committed is lost, effects never ran.
- **Does Suspense work with `useEffect` fetching?** No; only sources that suspend (throw/`use` a promise).

## Say it in 60 seconds
Concurrency in React means rendering is interruptible and prioritized, not parallel. `startTransition` marks a state update as non-urgent, so keystrokes commit immediately while the heavy list renders in the background in small slices, and stale renders get thrown away. If I don't own the update, `useDeferredValue` gives me a lagging copy of the value to feed a memoized expensive child. Suspense declares loading boundaries, and inside a transition React keeps the old UI instead of flashing a fallback. It won't make a slow render faster or fix long tasks outside React, so I still profile, and often virtualize.
