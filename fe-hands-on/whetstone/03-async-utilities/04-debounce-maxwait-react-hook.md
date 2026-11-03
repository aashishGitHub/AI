# Debounce with maxWait, flush and cancel, plus a React hook that never goes stale
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 15 min · **Tags:** debounce · throttle · react hooks
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
`debounce(fn, wait, { leading, trailing, maxWait })` with `cancel/flush/pending`, then `useDebouncedCallback` that always calls the latest closure and cleans up on unmount. (Site has React/Angular/Vue tabs; notes are React.)

Test cases given (fake timers): 3 calls 50 ms apart, wait 100 → one call 100 ms after the last, with last args; `leading: true, trailing: false` → first call immediate, rest ignored; `maxWait: 300` with calls every 100 ms → fires ~every 300 ms; `flush()` runs pending now, `cancel()` drops it; hook uses the new closure after re-render and cancels on unmount.

## Core answer (key points)
- Debounce = run after input has been **quiet** for `wait` ms, with the **latest** args.
- `leading` fires at the start of a burst; `trailing` at the end. With both, trailing only fires if there was another call during the window (no double call for a single click).
- `maxWait` guarantees a call at least every N ms during continuous input. **Throttle = debounce with `leading + trailing + maxWait = wait`.**
- `cancel()` drops pending, `flush()` runs pending now, `pending()` reports a scheduled call.
- React: keep the debounced function **stable** (memo on primitive options only) and call the **latest** callback through a ref. Otherwise re-renders reset the timer or the timer fires a stale closure.
- Cancel on unmount.

## Mental model / flow
```
calls:   x  x  x            x
time:    0  50 100          ...
trailing timer reset on each call ─► fires at 200 with args of call@100
maxWait timer started on first call of burst ─► forces a run at 300 even if calls continue
```

## Code sketch
```ts
type Opts = { leading?: boolean; trailing?: boolean; maxWait?: number };
export interface Debounced<A extends unknown[]> {
  (...args: A): void; cancel(): void; flush(): void; pending(): boolean;
}

export function debounce<A extends unknown[]>(
  fn: (...args: A) => void, wait: number, { leading = false, trailing = true, maxWait }: Opts = {},
): Debounced<A> {
  let quietTimer: ReturnType<typeof setTimeout> | undefined;
  let maxTimer: ReturnType<typeof setTimeout> | undefined;
  let queued: A | undefined;

  const fire = () => { const a = queued; queued = undefined; if (a) fn(...a); };
  const stop = () => {
    clearTimeout(quietTimer); clearTimeout(maxTimer);
    quietTimer = maxTimer = undefined;
  };
  const onQuiet = () => { stop(); if (trailing) fire(); queued = undefined; };

  const d = ((...args: A) => {
    const burstStart = quietTimer === undefined;
    queued = args;
    if (burstStart && leading) fire();
    clearTimeout(quietTimer);
    quietTimer = setTimeout(onQuiet, wait);
    if (maxWait !== undefined && maxTimer === undefined) {
      maxTimer = setTimeout(() => { maxTimer = undefined; fire(); }, maxWait);
    }
  }) as Debounced<A>;

  d.cancel = () => { stop(); queued = undefined; };
  d.flush = () => { if (quietTimer !== undefined) { stop(); fire(); } };
  d.pending = () => quietTimer !== undefined;
  return d;
}

export const throttle = <A extends unknown[]>(fn: (...a: A) => void, ms: number) =>
  debounce(fn, ms, { leading: true, trailing: true, maxWait: ms });
```
React hook:
```tsx
export function useDebouncedCallback<A extends unknown[]>(
  cb: (...args: A) => void, wait: number, opts: Opts = {},
) {
  const latest = useRef(cb);
  useLayoutEffect(() => { latest.current = cb; });

  const { leading, trailing, maxWait } = opts;
  const d = useMemo(
    () => debounce((...a: A) => latest.current(...a), wait, { leading, trailing, maxWait }),
    [wait, leading, trailing, maxWait],
  );
  useEffect(() => () => d.cancel(), [d]);
  return d;
}

function Search({ onQuery }: { onQuery: (q: string) => void }) {
  const run = useDebouncedCallback(onQuery, 300);
  return <input type="search" onChange={(e) => run(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && run.flush()} onBlur={() => run.flush()} />;
}
```
Updating the ref in a layout effect avoids a render-phase side effect; assigning `latest.current = cb` during render is common and works, but is technically impure. React's `useEffectEvent` is the official primitive for "latest callback" (I believe it's stable as of React 19.2; verify for your version).

## Trade-offs & pitfalls
- My version clears and re-arms the quiet timer on every call; lodash instead keeps one timer and re-arms for the *remaining* time on expiry, which is cheaper under very high call rates.
- Memo deps must be primitives; an inline `{ maxWait: 500 }` object would recreate the debouncer every render.
- `Date.now()` can jump (sleep, clock change); `performance.now()` is monotonic if you compute elapsed time.
- Always `flush` on Enter/blur so the last input isn't lost; `cancel` on unmount.
- Debounce reduces *calls*; it doesn't make rendering cheaper. For expensive renders of typed input, `useDeferredValue` is the tool.

## Likely follow-ups
- **Debounce the callback or the value?** With TanStack Query, debouncing the query key (`useDebouncedValue(term, 300)`) is often cleaner; the library handles cancellation and caching.
- **Throttle vs debounce for scroll?** Throttle (regular updates) or rAF-throttle for visual work; debounce for "after the user stops".
- **Why does the stale closure happen?** A debouncer created once captures the first render's `cb`; the ref indirection reads the current one at call time.
- **Angular/Vue?** RxJS `debounceTime`/`throttleTime` in Angular; in Vue a composable with `onUnmounted(cancel)` or `watchDebounced` from VueUse.

## Say it in 60 seconds
Debounce runs the function once input has been quiet for `wait` milliseconds, using the latest arguments. The production version adds leading and trailing edges, and maxWait, which forces a call at least every N milliseconds during continuous input; throttle is just debounce with leading, trailing and maxWait equal to wait. It exposes cancel, flush and pending, and you flush on Enter or blur so the last input isn't lost. In React the two failure modes are re-creating the debouncer every render, which resets the timer, and the timer firing a stale closure. So I memoise the debouncer on primitive options only, call the latest callback through a ref updated in a layout effect, or `useEffectEvent` where available, and cancel in the unmount cleanup.
