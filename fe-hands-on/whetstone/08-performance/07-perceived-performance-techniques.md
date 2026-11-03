# Perceived performance: skeletons, optimistic UI, prefetching on intent and view transitions
**Round:** 08 · Performance · **Level:** Senior · **Time:** 12 min · **Tags:** perceived performance · skeletons · optimistic ui
Source: https://whetstone-v1.vercel.app/#performance

Scenario: a dashboard takes 1.2 s to load data and feels slow; a competitor with similar timings feels instant. Improve perception without touching the backend. (Site offers React/Angular/Vue code; notes use React.)

## What they're really testing
Whether you know that perceived speed is about feedback and continuity, the specific UI patterns, their failure modes, and how you'd measure perception.

## Core answer (key points)
- **Instant feedback:** respond visually to every input within ~100 ms (pressed/pending states, optimistic updates).
- **Skeletons over spinners** for content with known shape; must match final layout to avoid CLS.
- **Keep previous content** during filter/page/tab changes (dim it, inline spinner) instead of blanking to a loader.
- **Optimistic UI** for low-risk mutations (likes, toggles, reorder, add comment) with defined rollback UX on failure.
- **Prefetch on intent:** hover/focus/viewport triggers prefetch of both data and code; respect `Save-Data` and mobile bandwidth.
- **Progressive rendering:** streaming SSR and Suspense boundaries so the shell and fast parts show first; avoid "popcorn" layouts with too many independent spinners.
- **View transitions:** connect list → detail visually; respect `prefers-reduced-motion`; don't block navigation on long animations.
- **Measure perception:** INP, time to useful content (custom marks like "first chart rendered"), CLS, plus user research/session feedback. None of this replaces real speed.
- **Thresholds (Nielsen-style):** < 100 ms feels instant, ~1 s keeps flow, > 10 s needs progress, an estimate and a way to do something else.

## Mental model / flow
| Technique | Good for | Watch out |
|---|---|---|
| Optimistic update | likes, toggles, reorder | rollback UX, concurrent edits |
| Skeleton | known-shape content | must match final size (CLS) |
| Keep previous data | filters, pagination, tabs | signal staleness |
| Prefetch on intent | links, next step | wasted bandwidth, Save-Data |
| Progressive render | streaming SSR, Suspense | popcorn layout |
| View transitions | route changes, list→detail | reduced motion, long animations |

## Code sketch
```tsx
// Prefetch data + code on intent (TanStack Query style).
function ReportLink({ id, children }: { id: string; children: React.ReactNode }) {
  const qc = useQueryClient();
  const warm = () => {
    void qc.prefetchQuery({ queryKey: ['report', id], queryFn: () => getReport(id), staleTime: 30_000 });
    void import('./routes/ReportPage');
  };
  return <Link to={`/reports/${id}`} onPointerEnter={warm} onFocus={warm}>{children}</Link>;
}

// Optimistic toggle with rollback.
const toggleStar = useMutation({
  mutationFn: (id: string) => api.star(id),
  onMutate: async (id) => {
    await qc.cancelQueries({ queryKey: ['items'] });
    const prev = qc.getQueryData<Item[]>(['items']);
    qc.setQueryData<Item[]>(['items'], (xs) => xs?.map((x) => (x.id === id ? { ...x, starred: !x.starred } : x)));
    return { prev };
  },
  onError: (_e, _id, ctx) => { qc.setQueryData(['items'], ctx?.prev); toast('Could not save, reverted'); },
  onSettled: () => qc.invalidateQueries({ queryKey: ['items'] }),
});

// Keep previous data on filter change.
useQuery({ queryKey: ['rows', filter], queryFn: () => getRows(filter), placeholderData: keepPreviousData });
```
```ts
function withViewTransition(update: () => void) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!document.startViewTransition || reduce) return update();
  document.startViewTransition(() => flushSync(update)); // DOM must be updated inside the callback
}
```

## Trade-offs & pitfalls
- Optimistic UI on high-stakes actions (payments, deletes with side effects) misleads users; use pending states there.
- Skeletons that flash for 50 ms are worse than nothing; delay showing them (~200 ms) or use a minimum display time.
- Aggressive prefetch hurts mobile data and server load; prefer hover-with-delay or viewport + idle, cap concurrency.
- View transitions: same-document API needs synchronous DOM update in the callback (hence `flushSync` in React); cross-document (`@view-transition { navigation: auto; }`) is newer and browser support varies, verify.
- Too many Suspense boundaries → content popping in random order; group related content.

## Likely follow-ups
- **Skeleton vs spinner?** Skeleton for content areas with known shape (sets expectation, reserves space); spinner for short indeterminate actions in a small area.
- **How do you handle optimistic conflicts?** Server is source of truth; on settle refetch/reconcile; version fields or last-write-wins policies explicit.
- **What metric proves it worked?** A custom "time to useful content" mark, INP, task completion time, and qualitative feedback; perceived wins may not move LCP.
- **How does `useTransition` help perception?** Keeps old UI interactive and visible while the new state renders, avoiding fallback flashes.
- **Save-Data?** Check `navigator.connection?.saveData` or the `Save-Data` request header and skip speculative prefetch.

## Say it in 60 seconds
Users judge speed by feedback and continuity, not just milliseconds. So I make every interaction respond within about a hundred milliseconds with pressed or pending states, and use optimistic updates for low-risk actions like stars and toggles, with a clear rollback if the server says no. For loading I show skeletons that match the final layout instead of spinners, and when filters or tabs change I keep the previous data visible and dimmed instead of blanking the page. I prefetch both the data and the route code on hover or focus, stream the shell first with Suspense, and use view transitions so list-to-detail feels connected, respecting reduced motion. I measure with INP and a custom time-to-useful-content mark plus user feedback, and I'm clear these tricks make good speed feel great; they don't replace it.
