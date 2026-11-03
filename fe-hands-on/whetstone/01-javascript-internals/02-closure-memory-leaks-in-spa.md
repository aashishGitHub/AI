# How do closures cause memory leaks in a long-lived SPA, and how do you find them?
**Round:** 01 · JavaScript Internals · **Level:** Senior · **Time:** 15 min · **Tags:** closures · memory · garbage collection
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Do you understand reachability (not "closures are bad"), can you run a disciplined DevTools workflow, and do you have a structural prevention pattern (ownership + cleanup).

## Core answer (key points)
- GC frees what is **unreachable from roots** (globals, the stack, live handles like timers and listeners).
- A function object references its lexical environment, so **as long as the function is reachable, everything it captured is reachable**.
- Leaks = something long-lived (window listener, interval, module cache, store subscription) holds a callback that captured something big (detached DOM, old component state, chart instance).
- Engine detail: closures created in the same scope often **share one context object**. A long-lived callback can keep alive a variable that only a sibling closure used. Keep long-lived callbacks in small scopes. (Exact behaviour is engine-specific.)
- Find it: repeat a memory-neutral action N times, diff heap snapshots, look for objects growing by N and for "Detached" DOM, read retainer paths back to a root.
- Prevent it: every subscription has an **owner** and a **cleanup**. `AbortController` as owner makes teardown a single `abort()`.

## Mental model / flow
```
GC root: window
  └─ listeners["resize"]
       └─ onResize (closure)
            └─ [[Scope]] { bigTable, rowCache, chart }   <- all kept alive
```
Common suspects and fixes:

| Leak source | Why it survives | Fix |
|---|---|---|
| `addEventListener` on window/document | target outlives component | remove in cleanup or `{ signal }` |
| `setInterval` / recursive `setTimeout` | timer is a root | clear in cleanup |
| store / socket / observer subscriptions | emitter holds callback | `unsubscribe()` / `disconnect()` |
| module-level `Map` keyed by objects | strong keys | `WeakMap` or bounded LRU |
| cached DOM nodes in variables | JS ref keeps detached tree | null refs, don't cache globally |
| debug hooks on `window` | global root | dev-only or remove |
| pending promises chained to big data | reaction keeps scope | abort and settle requests |

DevTools workflow:
1. Pick an action that should be memory-flat (open/close modal, A→B→A). Repeat 10x.
2. Force GC, snapshot before; repeat; force GC, snapshot after.
3. Comparison view, sort by delta. Count deltas of exactly 10 = suspects.
4. Filter "Detached".
5. Retainers panel: walk the chain to the root (Window → listener → closure → context → table).
6. Verify fix with the same loop and a flat line in Performance monitor / allocation timeline.

## Code sketch
```ts
function useWindowListener<K extends keyof WindowEventMap>(
  type: K,
  handler: (e: WindowEventMap[K]) => void,
) {
  const latest = useRef(handler);
  latest.current = handler;

  useEffect(() => {
    const owner = new AbortController();
    window.addEventListener(type, (e) => latest.current(e), { signal: owner.signal });
    return () => owner.abort();
  }, [type]);
}
```
One signal can own listeners, `fetch` calls and custom subscriptions for a whole feature.

## Trade-offs & pitfalls
- Turning off React StrictMode to stop "double subscriptions" hides exactly the missing-cleanup bugs it exposes.
- `WeakMap` only helps when the *key* is the thing that should die; it does nothing for values kept by other references.
- Heap snapshots are themselves heavy; on huge heaps use allocation sampling first.
- Production signal: `performance.measureUserAgentSpecificMemory()` needs cross-origin isolation; otherwise rely on RUM heap trends vs session length.

## Likely follow-ups
- **Does React leak if I forget cleanup?** React releases unmounted fibers, but a listener you put on `window` still holds your closure and everything it captured.
- **WeakMap vs WeakRef here?** WeakMap to attach data to objects you don't own; WeakRef only for caches that tolerate the value vanishing.
- **How do you catch regressions in CI?** Playwright/Puppeteer loop a flow and assert JS heap (via CDP metrics) stays in a band; Meta's memlab automates detached-node analysis.
- **Why are detached nodes so expensive?** One retained node keeps its whole subtree plus any listeners and data on it.

## Say it in 60 seconds
A closure keeps its scope alive as long as the function is reachable, so leaks come from something long-lived, like a window listener, an interval, a module cache or a store subscription, holding a callback that captured something large, usually detached DOM or stale component state. Engines often share one context object across sibling closures, so keep long-lived callbacks in small scopes. To find a leak I repeat a memory-neutral action ten times, diff heap snapshots after forcing GC, look for counts that grew by ten and for detached nodes, and read the retainer path back to the root. To prevent it, every subscription gets an owner and a cleanup; an AbortController per feature makes teardown one call, and StrictMode's double-mount is the cheap early warning.
