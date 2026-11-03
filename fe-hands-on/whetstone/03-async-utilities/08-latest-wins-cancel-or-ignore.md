# Stale responses: cancel or ignore? Build a "latest wins" helper and know when to use each strategy
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 12 min · **Tags:** race conditions · abortcontroller · switchmap
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
Out-of-order responses overwriting newer UI. Build `latest(fn)` so only the most recent call matters, and know the full strategy menu (switch / concat / exhaust / merge) and when cancel is unsafe. (Site has React/Angular/Vue tabs; notes are framework-neutral plus React.)

Test cases given: slow call 1 then fast call 2 → call 1 resolves `{ stale: true }`, call 2 `{ stale: false, value }`; call 1's signal aborts as soon as call 2 starts; a superseded call's error is reported as stale, the latest call's real error propagates.

## Core answer (key points)
- Two mechanisms, best combined:
  - **Ignore**: tag each call with a version; only apply if it's still the latest.
  - **Cancel**: abort the previous request's `AbortController` to save bandwidth/server work.
- Abort the previous *and* guard the write; abort alone isn't enough if the old one resolves just before the abort lands.
- Superseded calls resolve as `{ stale: true }` (not rejected), so callers don't show bogus errors.
- **Cancel ≠ undo.** Aborting a fetch stops the client waiting; a server mutation may already have happened. Never use "cancel previous POST" as a consistency mechanism.
- Strategy menu (RxJS names): **switchMap** latest wins; **concatMap** queue in order; **exhaustMap** ignore new while busy; **mergeMap** all in parallel.

| Situation | Strategy |
|---|---|
| typeahead, filters, route data | switch (cancel old) |
| saving edits to one document | concat (never reorder writes) |
| submit double-click | exhaust (or disable the button) |
| independent uploads | merge (with a pool limit) |

## Mental model / flow
```
call#1 (v1) ── fetch ─────────────── resolves ─► v1 != current ─► { stale: true }
call#2 (v2) ─ abort(#1) ─ fetch ── resolves ─► v2 == current ─► { stale: false, value }
```

## Code sketch
```ts
type Latest<R> = { stale: false; value: R } | { stale: true };

export function latest<A extends unknown[], R>(fn: (signal: AbortSignal, ...args: A) => Promise<R>) {
  let current: AbortController | undefined;
  let version = 0;

  return async (...args: A): Promise<Latest<R>> => {
    current?.abort(new DOMException('Superseded', 'AbortError'));
    const mine = new AbortController();
    current = mine;
    const v = ++version;
    try {
      const value = await fn(mine.signal, ...args);
      return v === version ? { stale: false, value } : { stale: true };
    } catch (err) {
      if (v !== version) return { stale: true };
      throw err;
    }
  };
}

const findUsers = latest(async (signal, q: string) => {
  const r = await fetch(`/api/users?q=${encodeURIComponent(q)}`, { signal });
  if (!r.ok) throw new Error(String(r.status));
  return r.json() as Promise<unknown>;          // validate before trusting (Round 02 · Q06)
});

input.addEventListener('input', async () => {
  const res = await findUsers(input.value);
  if (!res.stale) render(res.value);
});
```
React effect equivalent: the cleanup is the abort point.
```tsx
useEffect(() => {
  const ctrl = new AbortController();
  loadUser(id, ctrl.signal).then(setUser, (e) => { if (!ctrl.signal.aborted) setError(e); });
  return () => ctrl.abort();
}, [id]);
```

## Trade-offs & pitfalls
- Ignore-only still wastes bandwidth and server time; cancel-only can leak a stale write in the narrow window before abort.
- For writes, use a **queue** (concat) or **versioned updates** (ETag + `If-Match`, server rejects stale writes) instead of cancellation.
- One `latest()` instance per logical stream: sharing it across two unrelated widgets makes them cancel each other.
- TanStack Query handles this by key automatically (and passes a `signal` to the query function).
- Angular: `switchMap` on the input stream; Vue: `watch` with `onCleanup`/`onWatcherCleanup` to abort.

## Likely follow-ups
- **Why resolve stale instead of rejecting?** Rejections from superseded calls look like real errors and trigger error UI/monitoring.
- **What about the server side?** Abort may not stop server work; for expensive queries the server should observe client disconnects.
- **How do you test it?** Controlled promises (deferreds): resolve call 2 first, then call 1, assert UI shows call 2 and call 1's signal was aborted.
- **exhaustMap vs disabling the button?** Both; the disabled button is UX, exhaust is the guarantee in code.

## Say it in 60 seconds
When requests overlap, as in typeahead, filters or tab switches, an older response can land after a newer one and overwrite it. There are two fixes and I combine them: cancel the previous request with an AbortController to save work, and tag each call with a version so only the latest one is applied, because an abort can lose the race. Superseded calls resolve as stale rather than rejecting, so no fake error shows. This is switchMap semantics; the alternatives are concat for ordered writes, exhaust for ignoring a double submit, and merge for independent parallel work. The key caveat is that cancelling a fetch doesn't undo a server mutation, so for writes I queue them or use versioned updates with ETags, never "cancel the previous POST". In React the effect cleanup is the abort point, and TanStack Query does this per key.
