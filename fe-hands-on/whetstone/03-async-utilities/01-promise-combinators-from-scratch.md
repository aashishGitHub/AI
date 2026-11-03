# Implement Promise.all, allSettled, any and race, and explain their failure semantics
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 15 min · **Tags:** promises · promise.all · allsettled
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
Writing the four combinators without natives, accepting any iterable of values/thenables, preserving input order, and nailing the empty-input and failure semantics.

Test cases given: `all([1, resolve(2), delay(10,3)])` → `[1,2,3]`; `all([delay(50,'a'), reject(x)])` rejects with `x` immediately; `any([reject(1), reject(2)])` → `AggregateError` with `errors [1,2]`; `all([])` → `[]`; `race([])` never settles.

## Core answer (key points)
| | resolves | rejects | empty input |
|---|---|---|---|
| `all` | all values, input order | first rejection | resolves `[]` |
| `allSettled` | array of `{status, value \| reason}` | never | resolves `[]` |
| `any` | first fulfilment | `AggregateError` when all reject (errors in input order) | rejects `AggregateError([])` |
| `race` | first settle | first settle | **pending forever** |

- Normalise every item with `Promise.resolve(item)`: handles plain values and foreign thenables.
- Store results **by index**, count completions; never `push` or trust `.length`.
- A promise settles once, so calling `resolve`/`reject` repeatedly is harmless: "first call wins" is free.
- Materialise the iterable once (`Array.from`): generators can't be re-iterated.
- Built-ins **don't cancel** losers. Cancellation needs an `AbortSignal` threaded into the work.

## Mental model / flow
```
items -> Promise.resolve each -> .then(onOk(i), onErr)
onOk(i): results[i] = v; if (--left === 0) resolve(results)
onErr:   reject(e)        // later calls no-op
```

## Code sketch
```ts
type Input<T> = Iterable<T | PromiseLike<T>>;

export function all<T>(input: Input<T>): Promise<Awaited<T>[]> {
  return new Promise((resolve, reject) => {
    const list = Array.from(input);
    const out = new Array<Awaited<T>>(list.length);
    let left = list.length;
    if (left === 0) return resolve(out);
    list.forEach((item, i) =>
      Promise.resolve(item).then((v) => {
        out[i] = v as Awaited<T>;
        if (--left === 0) resolve(out);
      }, reject),
    );
  });
}

export function allSettled<T>(input: Input<T>) {
  return all(Array.from(input, (item) =>
    Promise.resolve(item).then(
      (value) => ({ status: 'fulfilled' as const, value }),
      (reason: unknown) => ({ status: 'rejected' as const, reason }),
    ),
  ));
}

export function any<T>(input: Input<T>): Promise<Awaited<T>> {
  return new Promise((resolve, reject) => {
    const list = Array.from(input);
    const errors = new Array<unknown>(list.length);
    let left = list.length;
    if (left === 0) return reject(new AggregateError([], 'All promises were rejected'));
    list.forEach((item, i) =>
      Promise.resolve(item).then(resolve as (v: unknown) => void, (e) => {
        errors[i] = e;
        if (--left === 0) reject(new AggregateError(errors, 'All promises were rejected'));
      }),
    );
  });
}

export function race<T>(input: Input<T>): Promise<Awaited<T>> {
  return new Promise((resolve, reject) => {
    for (const item of input) Promise.resolve(item).then(resolve as (v: unknown) => void, reject);
  });
}
```
Typed object variant (handy in real code): `allProps({ user: getUser(), prefs: getPrefs() })` → `Promise<{ user: User; prefs: Prefs }>`, built on `Object.keys` + `all` + `Object.fromEntries`, with one contained assertion because `fromEntries` can't preserve key types.

## Trade-offs & pitfalls
- Unhandled rejections: in `all`, every item has `reject` attached, so later rejections are "handled" even after the first one wins.
- `results.push` breaks order; `results.length` lies with holes.
- `race` for timeouts doesn't stop the losing work; use `AbortSignal.timeout(ms)` passed to `fetch`.
- Thenable adoption costs extra microtask ticks; don't write tests that depend on exact tick counts.
- `allSettled` hides failures unless you inspect and report them.

## Likely follow-ups
- **Dashboard of 6 widgets, one slow/broken: which combinator?** `allSettled`, or independent queries per widget, so one failure is an error tile, not a blank page.
- **Timeout with race?** Race work vs a rejecting delay, *and* abort the work so it doesn't keep running.
- **Why does `any([])` reject but `all([])` resolve?** Vacuous truth: "all of none succeeded" is true; "at least one succeeded" is false.
- **Fail fast with cancellation?** Pass a shared `AbortController`; abort in the rejection handler (see Q02 pool).

## Say it in 60 seconds
`all` resolves with every value in input order or rejects with the first rejection; `allSettled` never rejects and reports each outcome; `any` resolves with the first fulfilment and only rejects with an AggregateError when everything fails; `race` settles like whichever settles first. Implementation-wise I convert the iterable to an array once, wrap each item in `Promise.resolve` so plain values and thenables both work, write results by index and count completions, and rely on the fact that a promise only settles once, so the first resolve or reject wins for free. Empty input is the trap: `all` resolves an empty array, `any` rejects, and `race` stays pending forever. None of them cancel the losers; that needs an AbortSignal.
