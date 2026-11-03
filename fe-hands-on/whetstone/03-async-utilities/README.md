# 03 · Async Patterns & JS Machine Coding
> The from-scratch utilities interviewers ask for, written to production standard: combinators, pools with cancellation, retries, debounce, caches, emitters, cloning, race handling · 9 questions · ~2 h 19 min
Source: https://whetstone-v1.vercel.app/#async-utilities

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Implement Promise.all, allSettled, any and race, and explain their failure semantics | Senior | 15 min | promises · promise.all · allsettled | [notes](01-promise-combinators-from-scratch.md) |
| 02 | Build a concurrency-limited task runner with cancellation, and avoid the classic bugs | Lead / Staff | 20 min | concurrency · promise pool · abortsignal | [notes](02-concurrency-pool-with-cancellation.md) |
| 03 | Retry with exponential backoff, full jitter, Retry-After and error classification | Senior | 15 min | retry · backoff · jitter | [notes](03-retry-backoff-jitter-retry-after.md) |
| 04 | Debounce with maxWait, flush and cancel, plus a React hook that never goes stale | Senior | 15 min | debounce · throttle · react hooks | [notes](04-debounce-maxwait-react-hook.md) |
| 05 | Request deduplication plus a cache with TTL, stale-while-revalidate and invalidation races | Lead / Staff | 18 min | caching · deduplication · stale-while-revalidate | [notes](05-dedup-cache-ttl-swr.md) |
| 06 | Implement a type-safe event emitter (on, off, once, error isolation) | Senior | 12 min | event emitter · pub sub · typescript | [notes](06-type-safe-event-emitter.md) |
| 07 | Deep clone with cycles, Map, Set and Date, and when to just use structuredClone | Senior | 12 min | deep clone · structuredclone · recursion | [notes](07-deep-clone-vs-structuredclone.md) |
| 08 | Stale responses: cancel or ignore? Build a "latest wins" helper and know when to use each strategy | Senior | 12 min | race conditions · abortcontroller · switchmap | [notes](08-latest-wins-cancel-or-ignore.md) |
| 09 | Promises vs async/await: what actually differs, with the ordering, error and parallelism traps | Senior | 20 min | promises · async await · microtasks | [notes](09-promises-vs-async-await.md) |

## How these connect
- **Foundations first (09, 01)**: async/await is syntax over promises; combinators are where "first settle wins" and index-ordered results come from. Round 01 Q01 (event loop) is the prerequisite.
- **Cancellation is the spine (02, 03, 08)**: one `AbortSignal` threads through the pool, the retry sleep and the latest-wins helper. Abort stops *waiting*, not server-side effects; idempotency keys and write queues handle that.
- **Freshness and races (05, 08)**: both guard writes with a version/generation counter so an old response can't overwrite new data. Same pattern, different scope (per-key cache vs per-call-site).
- **Time-based control (03, 04)**: backoff with jitter and debounce/throttle are both about shaping call timing; test both with fake timers.
- **Data structures (06, 07)**: emitter (snapshot iteration, error isolation, typed payloads) and clone (WeakMap for cycles) are classic machine-coding; both end in "use the platform" (`EventTarget`, `structuredClone`).
- Suggested order: 09 → 01 → 08 → 02 → 03 → 04 → 05 → 06 → 07. For each, the strong interview move is to say what the production library (p-limit, lodash, TanStack Query, mitt) does internally.
