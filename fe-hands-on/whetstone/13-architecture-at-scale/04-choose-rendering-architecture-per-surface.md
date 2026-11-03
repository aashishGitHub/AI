# Choose a rendering architecture: SPA, SSR, SSG/ISR, streaming, islands or React Server Components
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** rendering · ssr · ssg
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: marketing site + authenticated app + docs. Pick a rendering strategy per surface.

## What they're really testing
That you decide per route from explicit criteria rather than picking one framework-wide religion, and that you know hydration is the hidden cost of SSR.

## Core answer (key points)
- **Criteria:** content dynamism (static / per request / per user), interactivity level, SEO and first-paint importance, data freshness, ops constraints (servers, caching, team skill).
- **Strategy map:**
  | Strategy | First paint | Client JS cost | Server cost | Freshness | Fit |
  |---|---|---|---|---|---|
  | CSR/SPA | Slower (JS first) | Whole app | Static host | Live | Dashboards/editors behind auth |
  | SSR | Fast HTML | Full hydration | Per request | Live | Personalized + SEO |
  | SSR + streaming | Earliest meaningful paint | Selective hydration | Per request | Live | Pages with slow sub-parts |
  | SSG | Fastest | Hydration | Build time | Stale until rebuild | Docs, marketing |
  | ISR / edge revalidate | Fast | Hydration | Low | Bounded staleness | Catalogs, blogs |
  | Islands | Fast | Only islands | Low | Varies | Content + few widgets |
  | RSC | Fast | Only client components | Per request or cached | Live | Content/interactivity mix |
- **My pick for the scenario:** marketing = SSG/ISR at the edge; docs = SSG (or islands for search/playgrounds); authenticated app = SPA with route-level code splitting and skeletons, or SSR/RSC only if first-load matters a lot.
- **Keep options open:** a framework that allows per-route modes, data access behind a typed client, no window/DOM access at module top level.

## Mental model / flow
```
SSR timeline:  request -> HTML painted (FCP) -> JS download -> parse -> hydrate -> interactive
                                ^ user clicks here are delayed (hurts INP) ^
```
Reduce the gap: ship less JS, hydrate selectively with Suspense boundaries, or move non-interactive parts server-only (islands/RSC).

## Trade-offs & pitfalls
- SSR for logged-in dashboards: server cost and complexity, little SEO benefit; a fast SPA shell may be better.
- Hydration mismatches from `Date.now()`, random ids, locale/timezone differences between server and client.
- Caching personalized SSR HTML in a shared CDN cache leaks user data. Vary correctly or mark private.
- RSC adds a new mental model (server/client boundary, serialization rules) and couples you to framework support.
- SSG at large page counts: build time explodes; ISR or on-demand revalidation fixes that.

## Likely follow-ups
- **How do you measure the choice?** RUM LCP/INP per route on real devices, server cost per request, cache hit ratio.
- **Streaming vs plain SSR?** Streaming flushes the shell early and fills slow Suspense boundaries later, improving perceived speed.
- **Islands vs RSC?** Both minimize client JS; islands are per-widget hydration in mostly static pages, RSC is a component-level server/client split inside a React tree.
- **How do you avoid lock-in?** Keep domain logic and data clients framework-agnostic; isolate rendering-mode specifics in route files.

## Say it in 60 seconds
I decide per surface, based on how dynamic the content is, how interactive it is, whether SEO and first paint matter, and what we can operate. Marketing and docs are static and SEO-critical, so SSG or ISR at the edge, with islands for small interactive bits. The authenticated app is user-specific and highly interactive, so a code-split SPA is often the simplest win, moving to SSR with streaming or RSC only if first load is a measured problem. The hidden cost of SSR is hydration: content shows early but clicks wait for JS, which hurts INP, so I aim to ship less client JS. And I watch for hydration mismatches and never cache personalized HTML in shared caches.
