# useSyncExternalStore, tearing, and how state libraries integrate with concurrent React
**Round:** 04 · React Rendering & Internals · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** usesyncexternalstore · tearing · zustand
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Scenario: a homegrown store was fine on React 17 but shows two different numbers on screen under React 18 transitions. Can you name tearing, explain why interruptible render causes it, and implement the `subscribe`/`getSnapshot` contract correctly?

## Core answer (key points)
- **Tearing:** one committed UI shows different versions of the same external state, because the store mutated between rendering component A and component B during a sliced (concurrent) render. Impossible with fully synchronous rendering, possible once rendering yields.
- **`useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot?)`:** React reads the snapshot during render and checks it again before commit; if it changed, React re-renders synchronously so the whole tree agrees on one version.
- **Contract:**
  - `subscribe(cb)` returns an unsubscribe; keep it stable (module-level or memoized) or React resubscribes each render.
  - `getSnapshot()` must return the **same reference** when nothing changed. A new object each call = "changed every time" = infinite loop / error.
  - Selectors must not allocate new arrays/objects per call.
- **Why not `useState` + `useEffect` subscribe:** subscribes after paint (can miss updates), costs an extra render, can tear.
- **Libraries:** Redux (`useSelector`), Zustand, Jotai, TanStack Query use this hook (or its shim) internally today.
- **Trade-off:** external-store updates are always synchronous; you cannot make them non-blocking with `startTransition`. Need that? Keep the state in React (`useState`/`useReducer`) or a transition-aware library.

## Mental model / flow
```
concurrent render, slices:
  slice 1: <Header> reads store.count = 1
  ...yield... store.count = 2 (websocket)
  slice 2: <Sidebar> reads store.count = 2        ← tear
useSyncExternalStore: before commit re-check getSnapshot()
  changed? → throw away, render synchronously with 2 everywhere
```

## Code sketch
```ts
type Sub = () => void;

export function createStore<S>(initial: S) {
  let state = initial;
  const subs = new Set<Sub>();
  return {
    get: () => state,
    set(next: (s: S) => S) {
      const n = next(state);
      if (Object.is(n, state)) return;
      state = n;                       // immutable replace → new reference only on change
      subs.forEach(fn => fn());
    },
    subscribe(fn: Sub) {
      subs.add(fn);
      return () => { subs.delete(fn); };
    },
  };
}

export function useSlice<S, T>(store: ReturnType<typeof createStore<S>>, pick: (s: S) => T): T {
  const read = () => pick(store.get());
  return useSyncExternalStore(store.subscribe, read, read);
}

// Bad: filter allocates every call → loop
// useSlice(todoStore, s => s.items.filter(t => !t.done))
// Good: select stable slice, derive in render
// const items = useSlice(todoStore, s => s.items);
// const open = useMemo(() => items.filter(t => !t.done), [items]);
```

## Trade-offs & pitfalls
- Mutating state in place breaks snapshot comparison: reference doesn't change, UI never updates.
- Derived selectors need memoization (reselect-style, Zustand `useShallow`) if they return new objects.
- Missing `getServerSnapshot` throws during SSR/hydration.
- Every subscriber's selector runs on every store change; very hot stores with thousands of subscribers need batching or finer-grained stores (atoms).

## Likely follow-ups
- **When skip an external store entirely?** State that's local, or must participate in transitions/Suspense; React state + context split by volatility.
- **Is Context tear-proof?** Yes, it's React state, but it re-renders all consumers; no selector support built in.
- **What's the shim?** `use-sync-external-store/shim` for React <18 compatibility (package name as I recall; verify).
- **How would you test the fix?** Render two consumers, mutate the store inside a `startTransition`-driven render with a slow component, assert both show the same value.

## Say it in 60 seconds
Tearing is when one screen shows two versions of the same external store, which becomes possible once React can pause mid-render and the store changes in the gap. `useSyncExternalStore` fixes it: React reads a snapshot, re-checks it before committing, and if it moved, re-renders synchronously so everything agrees. The contract is a stable `subscribe` and a `getSnapshot` that returns the same reference when nothing changed; selectors that allocate a new array each call cause infinite loops, so I select stable slices and derive with `useMemo`. Redux, Zustand and Jotai all sit on this hook now. The catch is store updates are always sync, so if I need transitions I keep that state in React.
