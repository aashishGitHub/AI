# A repeatable React profiling workflow
**Round:** 08 · Performance · **Level:** Senior · **Time:** 15 min · **Tags:** profiling · react devtools · performance panel
Source: https://whetstone-v1.vercel.app/#performance

Scenario: the team says "the app is slow" and wants to wrap everything in `memo`. Describe a repeatable workflow to find and fix the problem. (Site offers React/Angular/Vue code; notes use React.)

## What they're really testing
Measurement discipline: a defined scenario, production build, browser trace to classify cost, React Profiler to attribute renders, fix the top cost, prove it, guard it. Pushback on blanket memoization.

## Core answer (key points)
1. **Define a scenario** precisely: "typing in the filter with 5,000 rows lags" → measure input-to-paint.
2. **Baseline in a production build** (dev React is far slower and misleading), CPU throttled ~4×, ideally also a real mid-range device.
3. **Browser Performance panel:** find the long task for the interaction and classify it: React render/commit (component frames, scheduler work), style/layout (purple), paint (green), or plain app code (sorting, JSON parsing, regex).
4. **React DevTools Profiler:** enable "Record why each component rendered". For the interaction's commit read:
   - flamegraph (wide bars = expensive subtree),
   - ranked chart (self time),
   - render reasons (which prop changed, context changed, hooks changed, parent rendered).
5. **Fix the dominant cause**, not everything: colocate state, split context, stabilize props, memoize the row (not the world), memoize expensive derivations, virtualize, or move compute out of render.
6. **Re-measure the same scenario**; put before/after numbers in the PR.
7. **Guard:** interaction benchmark in CI (Playwright + `performance.mark/measure`), or `<Profiler onRender>` thresholds in tests.
- **Why not memo everything?** It costs comparison work and memory on every render, is defeated by unstable props, and hides the real cause (state placed too high). The React Compiler (auto-memoization) changes this calculus where adopted; verify its status for the codebase.

## Mental model / flow
```
scenario ─► prod build + throttle ─► Performance panel (what kind of cost?)
                                         │
                 ┌───────────────────────┼─────────────────────┐
              React render            layout/paint          app code
                 │                        │                     │
         React Profiler: who/why   fix thrash/containment   optimize algorithm / worker
                 │
             fix top offender ─► re-measure ─► CI guard
```

## Code sketch
```tsx
import { Profiler, type ProfilerOnRenderCallback } from 'react';

const onRender: ProfilerOnRenderCallback = (id, phase, actualDuration, baseDuration) => {
  if (actualDuration > 16) {
    performance.mark(`slow:${id}:${phase}`);
    console.warn(`${id} ${phase} ${actualDuration.toFixed(1)}ms (no-memo cost ${baseDuration.toFixed(1)}ms)`);
  }
};

export function OrdersScreen() {
  return (
    <Profiler id="OrdersGrid" onRender={onRender}>
      <OrdersGrid />
    </Profiler>
  );
}
```
```ts
// Playwright interaction benchmark (sketch)
test('filter stays under budget', async ({ page }) => {
  await page.goto('/orders?seed=5000');
  const ms = await page.evaluate(async () => {
    const input = document.querySelector<HTMLInputElement>('#filter')!;
    performance.mark('start');
    input.value = 'acme';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
    return performance.measure('filter', 'start').duration;
  });
  expect(ms).toBeLessThan(100);
});
```

## Trade-offs & pitfalls
- Profiler measurements include DevTools overhead; compare relative numbers in the same setup.
- Profiling build (`react-dom/profiling`) can be shipped to a small slice of production for field data, but adds overhead; gate carefully.
- CI timing benchmarks are noisy; use generous thresholds, multiple runs, median, and stable runners.
- **Common findings:** context provider value recreated every keystroke; selectors returning new arrays (`items.filter(...)` inside `useSelector`); rows memoized but receiving inline callbacks; derived data recomputed every render; many components measuring layout (thrash).

## Likely follow-ups
- **`actualDuration` vs `baseDuration`?** Actual = time for this commit with memoization; base = estimated cost to render the subtree without any memo (worst case).
- **How do you see why a component rendered without DevTools?** why-did-you-render in dev, or log in `onRender`; React DevTools "highlight updates" for a visual pass.
- **When is memo the right fix?** Expensive child, stable props, parent re-renders often for unrelated reasons.
- **What if the cost is layout, not React?** Batch reads/writes, `ResizeObserver`, CSS containment.
- **How does concurrent rendering change profiling?** Transitions spread work across frames; look at commit timing and interaction latency, not just total render time.

## Say it in 60 seconds
I don't optimize from a hunch. First I pin down one scenario, like typing in a filter with five thousand rows, and measure it on a production build with the CPU throttled. The browser Performance panel tells me what kind of cost it is: React rendering, layout and paint, or plain app code. If it's React, I switch to the Profiler with "why did this render" on, and read the flamegraph and ranked view for the interaction's commit to see which components rendered, why and how long. Usually it's state too high, a context value changing every keystroke, or unstable props defeating memo. I fix the top offender, re-measure the same scenario, put before and after in the PR, and add an interaction benchmark or Profiler threshold so it doesn't regress. Blanket memo adds cost and hides the real cause.
