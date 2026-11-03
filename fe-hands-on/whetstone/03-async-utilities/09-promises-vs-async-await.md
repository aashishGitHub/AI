# Promises vs async/await: what actually differs, with the ordering, error and parallelism traps
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 20 min · **Tags:** promises · async await · microtasks
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
That async/await is **syntax over promises**, not a separate mechanism; when to use each; and the real-world traps: accidental sequencing, `return` vs `return await`, `forEach(async)`, floating promises.

Test cases given: predict output of a mixed snippet with `setTimeout`; which of `return fetchJson()` / `return await fetchJson()` lets a surrounding `catch` run; fix a loop that awaits independent requests one by one.

## Core answer (key points)
- An `async` function **always returns a promise**. `await x` = `Promise.resolve(x)`, suspend, resume in a **microtask** when it settles, throw on rejection.
- Same scheduling, same states. Real differences: readability with branches/loops, `try/catch/finally`, access to earlier values without nesting, better async stack traces.
- Use **await** for control flow; use **promise methods** for composition (`all`, `allSettled`, `race`, `any`) and for wrapping callback APIs (`new Promise`). `await Promise.all(...)` is the normal shape.
- Code before the first `await` runs **synchronously**.
- Most bugs: accidental sequential awaits, missing `await`, `return` without `await` inside `try`, `forEach(async ...)`.

## Mental model / flow
Own ordering puzzle:
```js
console.log('A');
setTimeout(() => console.log('T'), 0);
Promise.resolve().then(() => console.log('P1')).then(() => console.log('P2'));
(async () => {
  console.log('B');
  await undefined;
  console.log('R1');
  await undefined;
  console.log('R2');
})();
console.log('C');
```
Output: `A B C P1 R1 P2 R2 T`.
1. Sync: `A`, then the async body up to the first await (`B`), then `C`.
2. Microtask queue now `[P1, R1]`. `P1` runs and queues `P2`; `R1` runs and queues `R2`.
3. Queue `[P2, R2]` drains.
4. Only then the timer task: `T`.

(Assumes native promises in a modern engine, where `await` on a native promise costs one tick. Don't build logic on exact tick counts.)

## Code sketch
```ts
// sequential by accident: ~ t1 + t2
const a = await getUser(id);
const b = await getOrders(id);

// parallel: ~ max(t1, t2)
const [user, orders] = await Promise.all([getUser(id), getOrders(id)]);

// loop over independent items
for (const id of ids) await save(id);          // sequential, only if order/limits require it
await Promise.all(ids.map(save));               // parallel; use a pool (Q02) to cap concurrency
ids.forEach(async (id) => { await save(id); }); // BUG: nobody waits, rejections float

// return vs return await inside try
async function withFallback() {
  try {
    return await fetchJson('/api');   // rejection caught below
    // return fetchJson('/api');      // rejection escapes; catch never runs
  } catch {
    return FALLBACK;
  }
}

// where new Promise is right: adapting a callback/event API
const waitFor = (el: EventTarget, type: string, signal?: AbortSignal) =>
  new Promise<Event>((resolve, reject) => {
    el.addEventListener(type, resolve, { once: true, signal });
    signal?.addEventListener('abort', () => reject(signal.reason), { once: true });
  });
```

## Trade-offs & pitfalls
- "Start early, await late" (`const p = getOrders(); const u = await getUser(); await p;`): if `p` rejects while you're awaiting `getUser`, it is briefly unhandled and may fire `unhandledrejection`. `Promise.all` attaches handlers immediately.
- Floating promises (no `await`, `return` or `.catch`) become unhandled rejections; lint with `@typescript-eslint/no-floating-promises`.
- `new Promise(async (resolve) => ...)`: errors thrown in the async executor are not captured by the outer promise.
- `.then(console.log())` passes `undefined`; pass the function.
- Promise chains: forgetting to `return` the inner promise in `.then` lets the outer chain continue early and swallows errors.
- `Promise.all` fails fast but doesn't cancel the rest; pair with an `AbortController`.
- Top-level await (ESM only) blocks evaluation of every importing module; keep it off shared entry points.

## Likely follow-ups
- **Does `await` always take one tick?** For native promises in modern engines, yes (V8 optimised this around 2018-19); foreign thenables take extra ticks to adopt. Don't depend on it.
- **Is async slower?** One promise per call plus the continuation; rarely measurable outside hot loops.
- **Timeout?** `Promise.race([work, delay(ms).then(() => { throw new TimeoutError(); })])`, and abort the work too (`AbortSignal.timeout`).
- **Error handling in parallel awaits?** `allSettled` to collect, or `all` inside `try` for fail-fast.
- **`async` in a `useEffect`?** Define an inner async function, call it, and abort in cleanup; the effect callback itself must not return a promise.

## Say it in 60 seconds
async/await isn't an alternative to promises, it's syntax over them. An async function always returns a promise, and `await` wraps its operand in a promise, suspends, and resumes in a microtask, throwing if it rejected. So scheduling and states are identical; what changes is readability with branches, loops and try/finally. I use await for control flow and promise combinators for composition, and `await Promise.all` is the normal shape. In ordering puzzles, code before the first await runs synchronously, each await continuation is queued behind already-queued then callbacks, and every microtask drains before any timer. The traps are awaiting independent calls one by one, `forEach` with an async callback which nobody waits for, returning a promise from inside `try` without awaiting it so the catch never runs, and floating promises, which a lint rule catches.
