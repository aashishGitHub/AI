# Request deduplication plus a cache with TTL, stale-while-revalidate and invalidation races
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** caching · deduplication · stale-while-revalidate
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
`AsyncCache.get(key, loader)` with TTL, SWR, `invalidate(key)` and dedupe; failures must not poison the cache; an invalidate during an in-flight load must not let the old response overwrite newer data.

Test cases given (fake timers): two concurrent `get('u1')` → loader once, same value; inside TTL no loader call; stale window returns old value and refreshes once in background; get → invalidate → slow old load resolves late → **not stored**; a rejecting loader isn't cached, next get retries.

## Core answer (key points)
- Per key keep: last settled value + timestamp, the in-flight promise (if any), and a **generation** number.
- **Dedupe**: concurrent callers share the in-flight promise.
- **Fresh** (age ≤ TTL): return value. **Stale** (TTL < age ≤ TTL + maxStale): return value now, start one background refresh. **Expired/missing**: await loader.
- **Failures**: never stored; clear the in-flight slot so the next call retries; keep serving the old stale value if there was one.
- **Invalidation race**: bump the key's generation; every write checks "is my generation still current?". Deleting the map entry alone doesn't help, the old `.then` still runs.

## Mental model / flow
```
t0 get(u1)          -> request A starts, gen 0
t1 invalidate(u1)   -> gen = 1, value dropped
t2 get(u1)          -> request B starts, gen 1
t3 B resolves       -> gen matches -> stored
t4 A resolves late  -> gen 0 != 1  -> ignored (would have shown pre-save data)
```

## Code sketch
```ts
type Slot<T> = { gen: number; hit?: { value: T; at: number }; inflight?: Promise<T> };

export class AsyncCache<T> {
  #slots = new Map<string, Slot<T>>();
  #ttl: number;
  #maxStale: number;

  constructor({ ttlMs, maxStaleMs = Infinity }: { ttlMs: number; maxStaleMs?: number }) {
    this.#ttl = ttlMs;
    this.#maxStale = maxStaleMs;
  }

  #slot(key: string): Slot<T> {
    let s = this.#slots.get(key);
    if (!s) this.#slots.set(key, (s = { gen: 0 }));
    return s;
  }

  #load(s: Slot<T>, loader: () => Promise<T>): Promise<T> {
    if (s.inflight) return s.inflight;
    const gen = s.gen;
    const p: Promise<T> = loader().then(
      (value) => {
        if (s.inflight === p) s.inflight = undefined;
        if (s.gen === gen) s.hit = { value, at: Date.now() };
        return value;
      },
      (err: unknown) => {
        if (s.inflight === p) s.inflight = undefined;
        throw err;
      },
    );
    s.inflight = p;
    return p;
  }

  get(key: string, loader: () => Promise<T>): Promise<T> {
    const s = this.#slot(key);
    if (s.hit) {
      const age = Date.now() - s.hit.at;
      if (age <= this.#ttl) return Promise.resolve(s.hit.value);
      if (age <= this.#ttl + this.#maxStale) {
        this.#load(s, loader).catch(() => {});   // background refresh; failure keeps stale value
        return Promise.resolve(s.hit.value);
      }
    }
    return this.#load(s, loader);
  }

  invalidate(key: string) {
    const s = this.#slots.get(key);
    if (!s) return;
    s.gen++;
    s.hit = undefined;
    s.inflight = undefined;                     // next get starts a fresh request
  }

  clear() { for (const key of this.#slots.keys()) this.invalidate(key); }
}
```
Callers already awaiting request A still receive A's (older) value; only the *cache write* is suppressed. Say that explicitly; if they must not see it, return a version with the value or re-read the cache.

## Trade-offs & pitfalls
- **Memory**: slots never shrink here. Bound with an LRU and garbage-collect unused keys after a period (TanStack Query's `gcTime`).
- **Keys**: derive from every input (`['user', id, { include: 'teams' }]`), serialised deterministically.
- **Cancellation**: pass an `AbortSignal` to loaders; abort when no subscribers remain.
- **Error caching**: not caching failures can hammer a dead backend; optionally cache errors briefly with backoff.
- **Reactivity**: a background refresh landing needs to re-render consumers, so a real cache needs `subscribe(key, fn)`. At that point you've rebuilt TanStack Query/SWR, which is the point to make.

## Likely follow-ups
- **`staleTime` vs `gcTime` in TanStack Query?** `staleTime` = how long data counts as fresh (no refetch); `gcTime` = how long an unused entry stays in memory.
- **Why the generation counter rather than comparing timestamps?** Responses can arrive out of order regardless of start time; a monotonically increasing token per key is unambiguous.
- **Optimistic updates?** Write the expected value, bump generation to discard in-flight reads, roll back on mutation failure, then invalidate.
- **HTTP-level SWR?** `Cache-Control: max-age=60, stale-while-revalidate=300` (RFC 5861) does the same at the browser/CDN layer.

## Say it in 60 seconds
Each key holds the last value with a timestamp, the in-flight promise and a generation number. Concurrent gets share the in-flight promise, which is the dedupe. Inside the TTL I return the value; in the stale window I return it immediately and kick off one background refresh; past that, callers wait for the loader. Failures are never stored: the in-flight slot is cleared so the next call retries, and an existing stale value keeps being served. The subtle part is invalidation: if a slow request started before an invalidate resolves after a newer one, it would overwrite fresh data, so invalidate bumps the generation and every write checks it. In production I'd use TanStack Query, which does exactly this plus subscriptions, garbage collection and cancellation, and I'd say so.
