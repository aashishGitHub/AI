# Build a concurrency-limited task runner with cancellation, and avoid the classic bugs
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Lead / Staff · **Time:** 20 min · **Tags:** concurrency · promise pool · abortsignal
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
`runPool(tasks, { limit, signal })`: at most `limit` in flight, results in input order, fail fast on first error, nothing new starts after failure/abort, and every task gets a signal so in-flight work can stop.

Test cases given: 10 tasks / limit 3 never exceeds 3 concurrent and keeps order; task 4 rejects → pool rejects with it, 5..10 never start; `abort()` mid-run rejects with the abort reason and aborts task signals; `limit: 0` → `RangeError`; `[]` → `[]`.

## Core answer (key points)
- Tasks are **functions** `(signal) => Promise<T>`, not promises: you must control when they start.
- Start `min(limit, n)` **workers**; each loops, pulling the next index from a shared cursor.
- `cursor++` needs no lock: JS runs one worker's synchronous code at a time.
- Store results by index.
- Track failure with a **separate boolean**: `throw undefined` and `Promise.reject()` are legal, so `if (firstError)` is a bug.
- On first error: set flag, record error, **abort the internal controller** so running tasks see it. Stopping scheduling ≠ cancellation; running work only stops if it honours the signal.
- Link the caller's signal (`AbortSignal.any` in modern runtimes, or a listener that aborts the internal controller).
- Wait for all workers before rejecting so nothing runs unobserved and cleanup is reliable.

## Mental model / flow
```
cursor ─► [w1] [w2] [w3]      each: while(!failed && !aborted && cursor < n) run(tasks[cursor++])
             │ error
             ▼
     failed = true; inner.abort(err) ──► in-flight tasks' fetch(signal) reject
     workers exit ──► Promise.all(workers) ──► throw first error | abort reason | results
```

## Code sketch
```ts
export type Task<T> = (signal: AbortSignal) => Promise<T>;

export async function runPool<T>(
  tasks: readonly Task<T>[],
  { limit, signal }: { limit: number; signal?: AbortSignal },
): Promise<T[]> {
  if (!Number.isInteger(limit) || limit < 1) throw new RangeError('limit must be a positive integer');
  signal?.throwIfAborted();

  const inner = new AbortController();
  const linked = signal ? AbortSignal.any([signal, inner.signal]) : inner.signal;
  const results = new Array<T>(tasks.length);
  let cursor = 0;
  let failed = false;
  let firstError: unknown;

  const worker = async () => {
    while (!failed && !linked.aborted && cursor < tasks.length) {
      const i = cursor++;
      try {
        results[i] = await tasks[i](linked);
      } catch (err) {
        if (!failed) { failed = true; firstError = err; inner.abort(err); }
        return;
      }
    }
  };

  await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, () => worker()));
  if (signal?.aborted) throw signal.reason;
  if (failed) throw firstError;
  return results;
}

const ctrl = new AbortController();
const urls = await runPool(
  files.map((f): Task<string> => async (s) => {
    const r = await fetch('/upload', { method: 'POST', body: f, signal: s });
    if (!r.ok) throw new Error(`upload ${r.status}`);
    return (await r.json()).url;
  }),
  { limit: 3, signal: ctrl.signal },
);
```
`async` function means the sync `RangeError` becomes a rejection, matching the test. `AbortSignal.any` is recent (2023-24 in browsers/Node 20.3+, to my knowledge); fall back to a manual listener for older targets.

## Trade-offs & pitfalls
- Waiting for all workers before rejecting delays the rejection until in-flight tasks notice the abort. If you need immediate rejection, reject early but still track workers for cleanup.
- External abort reason vs task error: check the caller's signal first so callers see *their* reason, not the derived `AbortError` from fetch.
- **Settled variant** for bulk UIs: don't stop on failure, store `{status, value|reason}` per index, keep pulling. Usually right when the UI shows per-item status.
- Remove any manual abort listeners in `finally` to avoid leaking closures on a long-lived signal.
- Complexity: O(n) scheduling, ≤ `limit` in flight, O(n) result memory.

## Likely follow-ups
- **Priorities?** Replace the cursor with a binary-heap priority queue; workers pop; allow pushes while running.
- **Per-task timeout?** `AbortSignal.any([linked, AbortSignal.timeout(ms)])` per task.
- **Retries?** Wrap each task with a retry helper that uses the same signal so cancel stops retries and sleeps (Q03).
- **Concurrency vs rate limiting?** Concurrency caps simultaneous requests; rate limiting caps starts per time window (token bucket). APIs returning 429 often need both.
- **What does p-limit do?** Same idea as a queue + active counter; returns a `limit(fn)` wrapper instead of a batch API.

## Say it in 60 seconds
Tasks are functions that take a signal, so I control start time. I spin up `limit` workers that each pull the next index from a shared cursor; that's safe without locks because only one worker's synchronous code runs at a time. Results go in by index so order is preserved. On the first error I set a separate failed flag, because the error itself can be undefined, record it, and abort an internal controller whose signal every task received, so new tasks never start and in-flight fetches are cancelled. The caller's signal is linked in with `AbortSignal.any`. I wait for all workers before rejecting so nothing is left running unobserved. Stopping scheduling is not cancellation; running work only stops if it honours the signal. For bulk UIs I'd offer a settled mode that keeps going and reports per item.
