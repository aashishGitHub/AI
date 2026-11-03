# Test custom hooks and async UI: fake timers, races and act() warnings
**Round:** 09 · Testing & Quality · **Level:** Senior · **Time:** 12 min · **Tags:** testing · hooks · fake timers
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: test a `useDebouncedSearch` hook (debounce, race handling, polling) and a data-fetching component. Tests are flaky and print "not wrapped in act(...)".

## What they're really testing
Deterministic control of time and promise ordering, choosing `renderHook` vs component tests, and understanding what the act warning signals.

## Core answer (key points)
- **Where to test:** if the hook is glue, test through the component that uses it. Use `renderHook` when the hook has real logic (debounce, cancellation, state machines).
- **Timers:** `vi.useFakeTimers()` (or Jest equivalent), then advance explicitly with `vi.advanceTimersByTime(ms)` inside `act`. Restore real timers after each test.
- **user-event with fake timers:** `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`, otherwise user-event's internal delays hang.
- **Races:** control resolution order with **deferred promises** (or MSW handlers with different delays). Start request A, then B, resolve B, then resolve A late, assert A's stale result didn't win.
- **Polling:** advance by the interval and assert call counts; assert it stops on unmount (no calls after `unmount()`).
- **Async UI:** `findBy*` for appearance, `waitFor` for later-true assertions; no arbitrary sleeps.
- **act() warning:** React saw a state update the test didn't wait for (a promise resolved or timer fired after your last assertion). Fix the cause: await the visible result, advance timers inside `act`, or `await act(async () => resolve(...))` for manual promises. Don't suppress console errors.
- **Hygiene:** fresh `QueryClient` per test with `retry: false`, shared provider wrapper, avoid asserting transient loading states unless required.

## Mental model / flow
```
Race test timeline (controlled):
t0 query 'r'   → request A (pending, deferred)
t1 query 're'  → request B (pending, deferred)
t2 resolve B   → state = B results
t3 resolve A   → must be IGNORED (stale)   ← assert state still = B

act(): "flush React work caused by this block before I assert"
```

## Code sketch
```ts
// Hook under test (illustrative): latest-wins search.
export function useSearchResults(q: string, search: (q: string) => Promise<string[]>) {
  const [results, setResults] = useState<string[]>([]);
  useEffect(() => {
    let current = true;
    search(q).then((r) => { if (current) setResults(r); });
    return () => { current = false; };
  }, [q, search]);
  return { results };
}
```
```ts
import { renderHook, act } from '@testing-library/react';

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

test('late response for an old query is ignored', async () => {
  const a = deferred<string[]>();
  const b = deferred<string[]>();
  const search = vi.fn().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);

  const { result, rerender } = renderHook(({ q }) => useSearchResults(q, search), { initialProps: { q: 'r' } });
  rerender({ q: 're' });

  await act(async () => b.resolve(['react']));
  await act(async () => a.resolve(['ruby', 'rust']));

  expect(result.current.results).toEqual(['react']);
});

describe('debounce', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test('fires once with the last value after the wait', () => {
    const cb = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(cb, 300));
    act(() => { result.current('a'); result.current('ab'); result.current('abc'); });
    act(() => { vi.advanceTimersByTime(299); });
    expect(cb).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith('abc');
  });

  test('polling stops after unmount', () => {
    const fetcher = vi.fn().mockResolvedValue([]);
    const { unmount } = renderHook(() => usePolling(fetcher, 5_000));
    act(() => { vi.advanceTimersByTime(10_000); });
    const calls = fetcher.mock.calls.length;
    unmount();
    act(() => { vi.advanceTimersByTime(20_000); });
    expect(fetcher).toHaveBeenCalledTimes(calls);
  });
});
```

## Trade-offs & pitfalls
- Fake timers + real promises: advancing timers doesn't flush microtasks automatically; use `await vi.advanceTimersByTimeAsync(ms)` (Vitest) when timers and promises interleave.
- Fake timers can break libraries that rely on `setTimeout` for internal scheduling (e.g., some animation or query libs); scope them to the tests that need them.
- Faking `Date` too (Vitest fakes it by default with `useFakeTimers`; verify config) can surprise date logic.
- `renderHook` tests can over-specify implementation; keep assertions on the hook's public return value.
- `let resolve!:` uses TS definite-assignment; safe because the Promise executor runs synchronously.
- Ignoring stale responses with a flag doesn't cancel the network; for real cancellation use `AbortController` and test that `abort` was signaled.

## Likely follow-ups
- **Why does `waitFor` hang with fake timers?** Older setups; RTL detects Jest fake timers and advances them, but with Vitest you may need `advanceTimersByTimeAsync` or real timers for that test. Verify for your versions.
- **How do you test with MSW instead of deferreds?** Give the first request a longer `delay()` than the second, then assert final UI shows the second.
- **renderHook with providers?** Pass `{ wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider> }`.
- **Is `act` needed with Testing Library?** RTL wraps render, user-event and `findBy`/`waitFor` in act; you need it explicitly for manual timer advances and manual promise resolution.
- **How do you test AbortController cancellation?** Spy on the fetcher's `signal` argument and assert `signal.aborted` after rerender/unmount.

## Say it in 60 seconds
I test hooks through the component when they're just glue, and with renderHook when they hold real logic like debounce or race handling. For timers I switch to fake timers and advance them explicitly inside act, and I tell user-event about them so it doesn't hang. For races I don't rely on timing at all: I return deferred promises from the fetcher, trigger two queries, resolve the newer one, then resolve the older one late, and assert the stale result didn't overwrite the new one. For polling I advance by the interval, count calls, and check it stops after unmount. The act warning means React processed an update the test didn't wait for, so I fix it by awaiting the visible result or resolving inside act rather than silencing the console. And every test gets a fresh QueryClient with retries off.
