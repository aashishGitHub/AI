# Iterators, generators and async iterators: when do they earn their place in UI code?
**Round:** 01 · JavaScript Internals · **Level:** Senior · **Time:** 12 min · **Tags:** iterators · generators · async iterators
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Protocol knowledge (`next`, `return`, `Symbol.iterator`/`asyncIterator`), lazy and cancellable pipelines, cleanup on early exit, and judgement about when this is overkill.

## Core answer (key points)
- **Iterator**: object with `next()` → `{ value, done }`. **Iterable**: has `[Symbol.iterator]()` returning one; consumed by `for...of`, spread, destructuring.
- **Generators** are the cheap way to write iterators: they pause at `yield`, resume on `next()`, so they're **lazy** and can be infinite.
- **Async iterators** (`[Symbol.asyncIterator]`, `for await...of`) model paginated APIs and streams: pull one page/chunk when the consumer is ready = natural backpressure.
- Early exit (`break`, `return`, `throw` in the loop) calls the iterator's **`return()`**, which runs the generator's `finally`. That makes iterators safe owners of resources.
- Combine with `AbortSignal` for cancellation on navigation.
- Overkill for a finite array you'll render anyway, for component state machines (use a reducer), and in hot numeric loops (protocol overhead).

## Mental model / flow
```
consumer: for await (row of paginate(...))
   │ next()
   ▼
generator: await fetchPage(cursor, signal) ─► yield* page.items ─► next cursor
   ▲                                                         │
   └──────────── break / abort ─► return() ─► finally { cleanup }
```

## Code sketch
```ts
type Page<T> = { items: T[]; next: string | null };

async function* pages<T>(
  load: (cursor: string | null, signal: AbortSignal) => Promise<Page<T>>,
  signal: AbortSignal,
): AsyncGenerator<T> {
  let cursor: string | null = null;
  try {
    do {
      const page = await load(cursor, signal);
      yield* page.items;
      cursor = page.next;
    } while (cursor && !signal.aborted);
  } finally {
    // runs on break, abort-driven throw, or normal completion
  }
}

const ctrl = new AbortController();
for await (const row of pages(fetchOrders, ctrl.signal)) {
  csv.write(serialize(row));
  if (csv.full) break;          // triggers return() -> finally
}
```
Sync lazy pipeline: write small `take`/`filter`/`map` generators, or use the built-in **iterator helpers** (`iter.filter(...).take(3).toArray()`) where supported.

Streams: `ReadableStream` is async-iterable in modern Chrome/Firefox/Node; Safari added it later, so feature-detect or fall back to `getReader()` in a loop. Verify current support.

## Trade-offs & pitfalls
- Generators add indirection; stack traces and debugging get harder.
- A `take(n)` that yields then checks the count avoids pulling an extra upstream item; order of `yield` vs counter check matters for side-effectful sources.
- Not serializable: can't put a generator in Redux state or send it to a worker.
- Calling `next()` after completion returns `{ value: undefined, done: true }` forever.
- Abort the fetch too (pass `signal` down), otherwise `break` stops consuming but the in-flight request still runs.

## Likely follow-ups
- **Why not recursion with promises for pagination?** Harder to cancel, no backpressure, accumulates everything, no clean `finally`.
- **Redux-Saga?** Used generators to describe effects as data (testable). Most teams moved to RTK Query/React Query and listeners; indirection cost outweighed the benefit.
- **How do you feed this to React?** Accumulate into state in batches (per page), or push into an external store and read with `useSyncExternalStore`.
- **What does `yield*` do?** Delegates to another iterable, forwarding `next`/`return`/`throw`.

## Say it in 60 seconds
An iterator is anything with a `next()` returning value and done; the iterable protocol lets `for...of` and spread consume it. Generators make writing them trivial and lazy, and async generators are the clean model for paginated APIs and streams because the consumer pulls one page at a time, which gives you backpressure. The killer property is that breaking out of a `for await` calls the generator's `return()`, so `finally` cleanup runs; add an AbortSignal and you get cancellation on navigation. I use them for sequential, possibly unbounded data like exports, CSV processing and streaming responses. For a finite array I'm going to render, plain array methods are clearer, and for UI state machines a reducer is better.
