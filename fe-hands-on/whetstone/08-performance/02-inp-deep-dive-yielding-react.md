# INP deep dive: long tasks, input delay, yielding, and React-specific fixes
**Round:** 08 · Performance · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** inp · long tasks · scheduler.yield
Source: https://whetstone-v1.vercel.app/#performance

Scenario: "Add to cart" feels sticky; p75 INP is 380 ms. The click updates React state, which re-renders a large list and runs analytics.

## What they're really testing
Decomposing an interaction into its three phases, seeing each in a trace, and knowing concrete React and scheduling fixes plus field attribution.

## Core answer (key points)
- **INP** ≈ the worst (high-percentile) interaction latency in a visit, measured click/tap/key → next frame painted. Three parts:
  1. **Input delay:** main thread already busy (hydration, a timer, a third-party script) when the event arrives.
  2. **Processing:** your event handlers (and the synchronous React render they trigger).
  3. **Presentation delay:** style, layout, paint, commit of the resulting DOM change.
- **Find it:** RUM with `web-vitals/attribution` gives the target element, phase breakdown, and Long Animation Frame (LoAF) script attribution. Lab: DevTools Performance with 4-6× CPU throttle, Interactions track, inspect the long task under it. Test on a real mid-range Android.
- **Fix by phase:**
  - Input delay → break up other long tasks, defer third parties, reduce hydration cost (selective hydration, less client JS).
  - Processing → do the visible update first, then **yield**, then the expensive work, then non-urgent work (analytics). Avoid sync `JSON.stringify`/localStorage writes in handlers.
  - Presentation → render less: smaller React update scope, memoized rows, virtualization, `content-visibility`.
- **React specifics for this scenario:**
  - Cart badge/button state is urgent; the big list re-render is not → wrap it in `startTransition` (interruptible, yields between units of work).
  - Why does the whole list re-render on add-to-cart? Usually a global store/context update consumed high in the tree. Subscribe to slices, colocate state, memo rows with stable props.
  - Analytics: fire after paint (`scheduler.yield()`, `requestIdleCallback`, or `sendBeacon` in a later task).
- **Commit:** p75 INP ≤ 200 ms per key route, tracked per release.

## Mental model / flow
```
event ─► [input delay] ─► [handler: setState → React render] ─► [commit → style/layout/paint] ─► frame
          busy thread       processing                            presentation delay

after fix:
event ─► setBadge() ─► yield ─► PAINT (user sees feedback)
                         └► startTransition(list update) ─► yield ─► analytics
```

## Code sketch
```ts
const yieldToMain = () =>
  'scheduler' in globalThis && 'yield' in (globalThis as any).scheduler
    ? (globalThis as any).scheduler.yield()
    : new Promise<void>((r) => setTimeout(r, 0));

async function onAddToCart(item: Item) {
  setPending(item.id, true);                 // urgent visual feedback
  await yieldToMain();                       // let the browser paint it
  startTransition(() => addItem(item));      // non-urgent list update, interruptible
  await yieldToMain();
  track('add_to_cart', { sku: item.sku });   // last
}
```
```ts
// Field/lab attribution via Long Animation Frames (Chromium).
new PerformanceObserver((list) => {
  for (const f of list.getEntries() as any[]) {
    if (f.duration > 100) console.table(f.scripts.map((s: any) => ({ src: s.sourceURL, fn: s.sourceFunctionName, ms: s.duration })));
  }
}).observe({ type: 'long-animation-frame', buffered: true });
```

## Trade-offs & pitfalls
- `setTimeout(0)` puts the continuation at the back of the task queue (other tasks can jump ahead); `scheduler.yield()` continues with priority. `scheduler.yield` is Chromium-first; polyfill. Verify current Safari/Firefox support.
- Yielding inside a handler means state can change between chunks; re-check assumptions after each `await`.
- `startTransition` doesn't make work cheaper; it makes it interruptible. If the list render is 300 ms, still reduce it.
- `useDeferredValue` is the read-side equivalent when you don't own the setter.
- Memoization without stable props (inline callbacks/objects) does nothing.
- Third parties (tag managers, chat, session replay, A/B) often dominate; use facades (load chat on click), defer, Partytown for some, and vendor budgets.

## Likely follow-ups
- **TBT vs INP?** TBT is a lab proxy summing long-task time during load; INP is field, about real interactions anytime in the visit.
- **Why did FID go away?** FID only measured input delay of the first interaction; INP (Core Web Vital since March 2024) covers all interactions and all three phases.
- **Long task vs long animation frame?** Long task = single task > 50 ms; LoAF = a frame delayed > 50 ms, aggregating multiple tasks plus rendering, with script attribution.
- **How does hydration hurt INP?** Clicks during hydration wait behind it; selective hydration prioritizes the clicked Suspense boundary.
- **What if the handler must do heavy CPU work?** Move it to a worker, show pending state immediately.

## Say it in 60 seconds
INP is roughly the worst interaction latency of a visit: input delay while the main thread is busy, processing in our handlers, and presentation delay while the result renders and paints. I'd confirm with web-vitals attribution which phase dominates for add-to-cart, and reproduce with a throttled CPU in the Performance panel. Here processing and presentation are the problem: one click re-renders a large list and runs analytics synchronously. So I update the button or badge first, yield so the browser paints, run the list update in a transition, and send analytics last. Then I fix the root cause: the list shouldn't re-render at all, so I subscribe to slices, memoize rows with stable props and virtualize. I hold the route to a p75 of 200 milliseconds and watch it per release.
