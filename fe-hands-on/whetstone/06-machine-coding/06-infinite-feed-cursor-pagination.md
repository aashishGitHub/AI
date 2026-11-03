# Infinite scrolling feed: cursor pagination, IntersectionObserver and scroll restoration
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 35 min · **Tags:** infinite scroll · pagination · intersectionobserver
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
A social feed that loads the next page near the bottom, handles errors, never duplicates, and restores list + scroll offset on back navigation.

Tests: sentinel in view → next page requested once even if it re-intersects while loading; an item already shown isn't rendered twice; failed page shows Retry that reloads the *same* cursor; back navigation restores list and offset; last page shows "You're all caught up".

## Core answer (key points)
- **Cursor pagination** (`?after=<opaque>`), not page numbers: inserts at the top don't shift pages and cause dupes/misses.
- **Sentinel + IntersectionObserver** with `rootMargin` (~1 viewport) to prefetch before the bottom.
- **One in-flight request:** guard with `isFetchingNextPage`/a ref; the observer may fire repeatedly.
- **Dedupe by id** when flattening pages — real backends still overlap.
- **Explicit states:** initial loading (skeleton), next-page loading, page error (Retry with the failed cursor), end of feed.
- **"Load more" button** inside the sentinel as accessible fallback; keyboard users otherwise can never reach the footer.
- **Data layer:** TanStack Query `useInfiniteQuery` (`getNextPageParam` → `nextCursor`, `signal` for abort, keeps cache across navigation). Or a small reducer if libraries are banned.
- **Scroll restoration:** keep pages cached (query cache / store outside the route), save `scrollY` per history entry (`history.state` or `sessionStorage` keyed by `location.key`), restore *after* items render. Native restoration fails when content isn't there yet.
- **Long sessions:** virtualize (variable heights) or drop far-away pages.
- **New posts while reading:** don't insert above the viewport; show a "5 new posts" pill.

## Mental model / flow
```
mount → page(null) → items + nextCursor
sentinel visible (rootMargin 800px) → if hasNext && !loading → page(nextCursor)
   ok    → append, dedupe by id
   error → show Retry(cursor) — same cursor, not next
nextCursor null → "You're all caught up"
navigate away → save scrollY in history state; cache retains pages
back          → render cached pages → restore scrollY (rAF after paint)
```

## Code sketch
```ts
// Library-free state machine (outline)
type FeedState = {
  items: Post[]; seen: Set<string>; cursor: string | null; done: boolean;
  status: 'idle' | 'loading' | 'error'; failedCursor: string | null;
};
type FeedAct =
  | { type: 'start' }
  | { type: 'page'; items: Post[]; next: string | null }
  | { type: 'fail'; cursor: string | null };

function feedReducer(s: FeedState, a: FeedAct): FeedState {
  switch (a.type) {
    case 'start': return { ...s, status: 'loading', failedCursor: null };
    case 'page': {
      const seen = new Set(s.seen);
      const fresh = a.items.filter(p => !seen.has(p.id) && seen.add(p.id));
      return { ...s, items: [...s.items, ...fresh], seen, cursor: a.next, done: a.next === null, status: 'idle' };
    }
    case 'fail': return { ...s, status: 'error', failedCursor: a.cursor };
  }
}
```
```tsx
function useSentinel(onVisible: () => void, rootMargin = '800px 0px') {
  const cb = useRef(onVisible);
  useLayoutEffect(() => { cb.current = onVisible; });
  return useCallback((el: HTMLElement | null) => {
    if (!el) return;
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) cb.current(); }, { rootMargin });
    io.observe(el);
    return () => io.disconnect();            // React 19 ref-callback cleanup
  }, [rootMargin]);
}

export function Feed({ fetchPage }: { fetchPage: (c: string | null, s: AbortSignal) => Promise<{ items: Post[]; next: string | null }> }) {
  const [s, dispatch] = useReducer(feedReducer, init);
  const inFlight = useRef<AbortController | null>(null);

  const load = useCallback(async (cursor: string | null) => {
    if (inFlight.current) return;
    const ac = (inFlight.current = new AbortController());
    dispatch({ type: 'start' });
    try { const r = await fetchPage(cursor, ac.signal); dispatch({ type: 'page', ...r }); }
    catch { if (!ac.signal.aborted) dispatch({ type: 'fail', cursor }); }
    finally { inFlight.current = null; }
  }, [fetchPage]);

  useEffect(() => { void load(null); return () => inFlight.current?.abort(); }, [load]);
  const sentinel = useSentinel(() => { if (!s.done && s.status === 'idle') void load(s.cursor); });
  useRestoreScroll(s.items.length > 0);      // read history.state.y, scrollTo after first render

  return (
    <section aria-label="Feed" aria-busy={s.status === 'loading'}>
      <div role="feed">
        {s.items.map((p, i) => <PostCard key={p.id} post={p} aria-posinset={i + 1} aria-setsize={s.done ? s.items.length : -1} />)}
      </div>
      {s.status === 'error' && <p role="alert">Couldn't load more. <button onClick={() => load(s.failedCursor)}>Retry</button></p>}
      {!s.done && s.status !== 'error' && (
        <div ref={sentinel}>
          <button onClick={() => load(s.cursor)} disabled={s.status === 'loading'}>
            {s.status === 'loading' ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
      {s.done && <p>You're all caught up.</p>}
    </section>
  );
}
```
(For a real app, swap the reducer for `useInfiniteQuery`; dedupe in a `useMemo` over `data.pages`. `aria-setsize=-1` means unknown in ARIA; verify AT support.)

## Trade-offs & pitfalls
- The `inFlight` ref matters: state-based guards lag a render behind the observer callback.
- An `IntersectionObserver` recreated every render reconnects and may fire again; keep the callback in a ref and the observer stable.
- Retry must use the failed cursor; using `s.cursor` after partial state updates can skip a page.
- Infinite scroll hurts SEO (crawlers don't scroll): provide paginated URLs.
- Scroll restoration with variable-height virtualized rows needs anchor-item + offset, not raw `scrollY`.

## Likely follow-ups
- **Why `rootMargin` not threshold?** Margin prefetches ahead of the viewport; threshold is about how much of the target is visible.
- **How do you avoid memory bloat?** Virtualize; or keep a window of pages and refetch evicted ones on scroll back.
- **Real-time inserts?** Buffer them; "N new posts" pill; on click prepend and scroll to top.
- **Testing?** Mock IntersectionObserver (trigger callback manually), MSW for pages/errors; Playwright for real scroll restoration.

## Say it in 60 seconds
I'd use cursor pagination so inserts at the top don't shift pages, and a sentinel element watched by an IntersectionObserver with a generous root margin to prefetch before the bottom. A ref guards a single in-flight request because the observer can fire repeatedly, and I dedupe by id when flattening pages since backends overlap. States are explicit: initial skeleton, next-page loading, an error row whose Retry reloads the same cursor, and an end-of-feed message. There's always a Load more button for keyboard and screen reader users. Pages stay cached outside the route and I save the scroll offset per history entry, restoring it after the items render. For long sessions I'd virtualize, and in production use `useInfiniteQuery`.
