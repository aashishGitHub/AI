# State architecture: server state, client state, URL state and form state. Who owns what?
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** state management · react query · redux
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: one global store holds server data, form drafts, UI toggles and URL filters. Bugs everywhere. Propose an architecture.

## What they're really testing
Can you classify state by owner and lifetime, and assign each kind to the tool built for it, then migrate without a rewrite.

## Core answer (key points)
- The root cause is mixing kinds of state with different owners, lifetimes and sync needs.
- **Classify first:**
  | Kind | Examples | Owner | Tool |
  |---|---|---|---|
  | Server | users, orders, permissions | Backend | TanStack Query / RTK Query / GraphQL client |
  | URL | filters, page, selected id | Router | typed, validated search params |
  | Form | drafts, dirty/touched, errors | Form | react-hook-form, `useActionState` |
  | Local UI | hover, open dropdown | Component | `useState` / `useReducer` |
  | Shared UI | theme, sidebar, toasts | App | rarely-changing Context or a tiny store |
  | Session | user, flags | Shell | Context provided once, or query cache |
- **Server state is a cache, not state you own:** it needs staleness, refetch, invalidation, dedupe. A cache library does this; Redux by hand does not.
- **URL is state:** makes views shareable, reload-safe and back-button-correct.
- Once server state leaves the store, the "global" remainder is usually tiny.
- **Migration:** move one domain's server data to a query cache per PR; move filters to URL; leave the store for true client globals. Add lint/review rules: no server responses in the store, no derived values stored.

## Mental model / flow
```
Need a value? ask: who is the source of truth?
  backend   -> query cache (key, staleTime, invalidate on mutation)
  URL       -> search params (parse + default)
  user typing, not yet submitted -> form
  only this component -> local state
  truly app-wide client state -> small store/context
```

## Code sketch
```ts
// Own sketch: URL as typed state with zod; invalid params fall back to defaults
const Filters = z.object({
  status: z.enum(['open', 'closed', 'all']).catch('open'),
  page: z.coerce.number().int().min(1).catch(1),
});

export function useFilters() {
  const [params, setParams] = useSearchParams();
  const filters = Filters.parse(Object.fromEntries(params));
  const setFilters = (patch: Partial<z.infer<typeof Filters>>) =>
    setParams(prev => {
      const next = new URLSearchParams(prev);
      Object.entries(patch).forEach(([k, v]) => next.set(k, String(v)));
      if (!('page' in patch)) next.set('page', '1'); // filter change resets paging
      return next;
    });
  return [filters, setFilters] as const;
}
```

## Trade-offs & pitfalls
- Copying server data into a store and syncing by hand -> stale lists, double sources of truth.
- Filters in component state -> broken back button and sharing.
- Selectors returning fresh objects from a giant store -> re-render storms.
- Storing values derivable from props/other state -> drift bugs. Derive during render.
- Context for frequently-changing values re-renders every consumer; use a store with selectors instead.

## Likely follow-ups
- **When is Redux still right?** Complex client-owned workflows (editors, undo/redo, offline queues) needing devtools and predictable reducers.
- **Optimistic updates?** In the query cache: snapshot, apply, roll back on error, invalidate on settle.
- **SSR and query cache?** Prefetch on server, dehydrate into HTML, hydrate on client.
- **How do you stop drift back?** Lint rules, ADR documenting the taxonomy, code review checklist.

## Say it in 60 seconds
Most state bugs come from mixing kinds of state. I'd classify by owner: server data belongs in a query cache that handles staleness and invalidation; filters, tabs and pagination belong in the URL so they're shareable and survive reloads; drafts belong in a form library until submit; UI toggles stay local; and only truly global client state like theme goes in a small store or context. Once server state leaves the global store, there's very little left. I'd migrate domain by domain, and lock it in with lint rules and an ADR so nobody puts API responses back into the store.
