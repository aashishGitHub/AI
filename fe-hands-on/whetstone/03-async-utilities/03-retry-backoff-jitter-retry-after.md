# Retry with exponential backoff, full jitter, Retry-After and error classification
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 15 min · **Tags:** retry · backoff · jitter
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
`retry(fn, options)`: delay `random(0, min(cap, base * 2^attempt))`, honour `Retry-After` (seconds or HTTP-date), classify errors, cancellable during the wait. Plus the system view: idempotency and where retries belong.

Test cases given (fake timers): fail twice then succeed → third call, two waits; 404 thrown immediately; 429 with `Retry-After: 2` waits ≥ 2000 ms; abort during wait rejects with the reason and makes no further call.

## Core answer (key points)
- **Retry only transient failures**: network errors, timeouts, 408, 425, 429, and 500/502/503/504, on idempotent requests.
- **Never retry** caller faults (400, 401, 403, 404, 422) or programming errors.
- **Full jitter**: uniform random in `[0, min(cap, base·2^n)]`. Spreads synchronised clients so a recovering server isn't hit in waves (AWS's architecture blog analysis found full jitter performs best among the variants they tested).
- **Server hint wins**: honour `Retry-After` when present, at least that long, bounded by your cap.
- Cap attempts and total time; stop immediately on abort, including mid-sleep.
- **Idempotency**: GET/PUT/DELETE are idempotent by spec, POST isn't. Use an idempotency key generated once per user intent and reused across retries; server dedupes.
- **Retry at one layer only.**

## Mental model / flow
```
attempt n ─► fn() ─ ok ─► return
               └ err ─► abort? / n >= max / !retryable ─► throw
                       └ delay = max(retryAfter, rand(0, min(cap, base*2^n)))  (bounded by cap)
                       └ abortable sleep(delay) ─► attempt n+1
```

## Code sketch
```ts
export class HttpError extends Error {
  status: number;
  retryAfterMs: number | null;
  constructor(status: number, retryAfterMs: number | null = null) {
    super(`HTTP ${status}`);
    this.name = 'HttpError';
    this.status = status;
    this.retryAfterMs = retryAfterMs;
  }
}

const TRANSIENT = new Set([408, 425, 429, 500, 502, 503, 504]);

export const isRetryable = (e: unknown) =>
  e instanceof DOMException && e.name === 'AbortError' ? false
  : e instanceof HttpError ? TRANSIENT.has(e.status)
  : e instanceof TypeError;               // fetch network failure

export function parseRetryAfter(h: string | null, now = Date.now()): number | null {
  if (!h) return null;
  const secs = Number(h);
  if (Number.isFinite(secs)) return Math.max(0, secs * 1000);
  const at = Date.parse(h);
  return Number.isNaN(at) ? null : Math.max(0, at - now);
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => { clearTimeout(t); reject(signal!.reason); };
    const t = setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(); }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });

export async function retry<T>(
  fn: (attempt: number) => Promise<T>,
  { retries = 3, baseMs = 300, capMs = 10_000, signal, shouldRetry = isRetryable,
    onRetry }: {
    retries?: number; baseMs?: number; capMs?: number; signal?: AbortSignal;
    shouldRetry?: (e: unknown, attempt: number) => boolean;
    onRetry?: (e: unknown, attempt: number, delayMs: number) => void;
  } = {},
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    signal?.throwIfAborted();
    try {
      return await fn(attempt);
    } catch (e) {
      if (attempt >= retries || !shouldRetry(e, attempt)) throw e;
      const jitter = Math.random() * Math.min(capMs, baseMs * 2 ** attempt);
      const hint = e instanceof HttpError ? e.retryAfterMs : null;
      const delay = hint === null ? jitter : Math.min(Math.max(hint, jitter), capMs);
      onRetry?.(e, attempt + 1, delay);
      await sleep(delay, signal);
    }
  }
}
```
Note: `return await` inside `try` is required, otherwise the rejection escapes the `catch` (see Q09). If a server's `Retry-After` exceeds your cap, decide explicitly: clamp (above) or give up and surface "try later".

## Trade-offs & pitfalls
- `TypeError` from fetch means network failure, but a `TypeError` from your own code looks identical. Keep the retried function narrow (just the request) so bugs aren't retried and hidden.
- **Retry amplification**: UI + client + gateway + service each retrying 3x turns one click into dozens of requests. Pick one layer, usually the data client (TanStack Query has `retry`/`retryDelay`).
- Add a **circuit breaker** or retry budget when many requests fail together.
- Long retries need UX: "Reconnecting…", with cancel.
- Test with fake timers and inject `Math.random` (or a `random` option) for determinism.

## Likely follow-ups
- **Why jitter at all?** Without it, everyone who failed together retries together at 1s, 2s, 4s: synchronised waves (thundering herd).
- **Decorrelated vs equal vs full jitter?** Variants trading average wait vs spread; full jitter is the simple default.
- **How do you make POST retries safe?** `Idempotency-Key` header per user intent (Stripe-style), server stores result by key.
- **Total time budget?** Track a deadline; skip a retry if `now + delay > deadline`.

## Say it in 60 seconds
I only retry transient failures: network errors, timeouts, 408, 429 and most 5xx, and only for idempotent requests; 4xx caller errors and bugs are thrown immediately. Between attempts I wait a uniformly random time between zero and the capped exponential, which is full jitter, so clients that failed together don't retry together. If the server sends Retry-After, in seconds or as an HTTP date, I wait at least that. The sleep is abortable, so cancel stops both the wait and further calls. For POSTs I attach an idempotency key generated once per user action so a retry can't double-charge. And I retry at exactly one layer, typically the data client, with a circuit breaker for widespread failure, because stacked retries multiply load on an already struggling service.
