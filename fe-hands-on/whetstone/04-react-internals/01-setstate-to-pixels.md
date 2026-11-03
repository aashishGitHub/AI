# What exactly happens between setState and pixels on screen?
**Round:** 04 · React Rendering & Internals · **Level:** Senior · **Time:** 15 min · **Tags:** react · reconciliation · fiber
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Whether you can narrate the full pipeline (schedule → render → commit → paint → passive effects) and tie each stage to a real bug class: lost state, layout flicker, impure render.

## Core answer (key points)
- **Trigger:** `setState` does not render. It queues an update object on that component's fiber, tags it with a priority lane, bubbles the lane up to the root and asks the scheduler to process the root.
- **Render phase (pure, interruptible):** React calls your component functions to get new element trees, then diffs them against the current fiber tree. `beginWork` walks down calling components and reconciling children; `completeWork` walks back up preparing DOM nodes off-screen and collecting the effect list. Nothing visible changes yet.
- **Reconciliation heuristic:** same element type + same key at the same position = keep the fiber and its state, update props. Different type or key = unmount the subtree and mount fresh.
- **Commit phase (synchronous, never paused):** before-mutation (`getSnapshotBeforeUpdate`), mutation (DOM insert/update/remove, detach old refs), layout (attach refs, `useLayoutEffect`, `componentDidMount/Update`).
- **Paint:** the browser paints after the commit's JS task finishes. Layout effects ran before this point, so they block paint.
- **Passive effects:** `useEffect` cleanups then setups run after paint (usually; a sync/discrete update can flush them earlier).
- **Batching:** since React 18, every update in the same tick is batched into one render, including in promises, timeouts and native listeners. `flushSync` is the escape hatch.
- **Purity:** render can run twice (Strict Mode in dev), be interrupted, or be thrown away. Side effects in render would run for UI that never commits. Strict Mode's double invoke exists to surface exactly that.

## Mental model / flow
```
setState ──► update queued on fiber, lane marked up to root
         ──► scheduler picks root by lane priority
RENDER   (pausable, discardable)
  beginWork   : call component, diff children
  completeWork: build DOM off-screen, collect effects
COMMIT   (sync)
  before-mutation → mutation (DOM) → layout (refs, useLayoutEffect)
PAINT    (browser)
PASSIVE  useEffect cleanup → setup
```

## Code sketch
```tsx
function Tooltip({ anchor }: { anchor: DOMRect }) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);

  useLayoutEffect(() => {
    // measured after DOM mutation, before paint: no flicker
    const h = ref.current!.getBoundingClientRect().height;
    setTop(anchor.top - h);
  }, [anchor]);

  useEffect(() => {
    analytics.track('tooltip_shown'); // after paint: not on the critical path
  }, []);

  return <div ref={ref} style={{ top }} role="tooltip" />;
}

// Classic reconciliation bug: component type defined inside render
function Form() {
  const Field = () => <input />; // new type each render → remount, focus lost
  return <Field />;
}
```

## Trade-offs & pitfalls
- Swapping `<div>` for `<section>` (or `<A>` for `<B>`) at the same slot discards the whole subtree's state.
- Index keys move state to the wrong row on insert/reorder. Use stable ids.
- Changing a `key` deliberately is the clean way to reset a component (`<Editor key={docId} />`).
- `useLayoutEffect` is paint-blocking; heavy work there hurts INP/LCP. Also warns on the server.
- `flushSync` forces a synchronous render; use only when you must read DOM right after the update (scroll to new item).

## Likely follow-ups
- **Is the virtual DOM why React is fast?** No. It is a programming model; diffing costs CPU. Speed comes from bounding work (keys, memo, colocation) and scheduling it.
- **useLayoutEffect vs useEffect?** Layout: after mutation, before paint, blocking; for measure-then-adjust. Everything else: `useEffect`.
- **useInsertionEffect?** Runs before layout effects so CSS-in-JS can inject styles before anyone measures.
- **What is a lane?** A bit in a priority bitmask. Discrete input is high, transitions are low, so a transition render can be interrupted and restarted.
- **Why fiber linked lists?** `child/sibling/return` pointers let React walk the tree iteratively and stop between units of work, which recursion cannot do.

## Say it in 60 seconds
`setState` just enqueues an update on the component's fiber with a priority lane and schedules the root. React then renders: it calls components and reconciles the new elements against the current fiber tree, keeping instances when type and key match and remounting when they don't. That phase is pure and, in concurrent mode, can pause or be discarded. Then it commits synchronously: DOM mutations, refs, layout effects. The browser paints, and only then do `useEffect`s run. Multiple updates in one tick are batched into one render. Because render may run more than once or never commit, it must be side-effect free, which is what Strict Mode's double render checks.
