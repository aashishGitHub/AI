# React Server Components: the mental model, the boundaries and the costs
**Round:** 04 · React Rendering & Internals · **Level:** Lead / Staff · **Time:** 20 min · **Tags:** rsc · server components · next.js
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Can you explain RSC well enough for a team to make an adoption decision (read-heavy dashboard with a few interactive widgets), including honest costs and a concrete boundary design?

## Core answer (key points)
- **Server Components** run only on the server (build or request time). They can be `async`, query data sources directly, and their code never ships to the client. Output is the **RSC payload**: a serialized tree with holes where Client Components go, plus those components' props.
- **Client Components** (`'use client'`) are normal React: they SSR to HTML, then hydrate and own state/effects/events.
- **The boundary is a module boundary.** `'use client'` marks an entry; everything that module imports is client code. Props crossing it must be serializable (no functions, except Server Functions).
- **Composition:** Server can render Client. Client cannot *import* Server, but can receive Server-rendered output as `children`/props from a Server parent. That's how a client layout wraps big server trees.
- **Gains:** less JS (markdown/date/highlighting libs stay server-side), data fetched close to the source without client→API→DB waterfalls, secrets stay server-side.
- **Costs:** two component kinds and a boundary to reason about; framework-specific caching layers ("why is this stale?"); server round trip for server-data interactions; tighter coupling to framework/bundler (Next App Router, or other integrations); testing and hosting changes.
- **Mutations:** Server Functions (`'use server'`) from forms/actions, then revalidate affected data/routes. Treat them as public endpoints.

## Mental model / flow
```
request
  └─ server renders Server Components (await data)
       → RSC payload (tree + client placeholders + props)
       → SSR HTML of the same tree, streamed, Suspense regions fill in later
browser
  └─ paint HTML → load JS only for Client Components → hydrate them
navigation
  └─ fetch new RSC payload → React merges → client state preserved
```

## Code sketch
Dashboard boundary design (illustrative, Next-style file layout):
```tsx
// app/dashboard/page.tsx  (Server)
export default async function Dashboard() {
  const [kpis, user] = await Promise.all([getKpis(), getUser()]); // parallel, no client waterfall
  return (
    <Shell user={user.name}>                 {/* server */}
      <KpiGrid data={kpis} />                {/* server, zero JS */}
      <Suspense fallback={<ChartSkeleton />}>
        <RevenueChartData />                 {/* server fetch, streams */}
      </Suspense>
      <DateRangeFilter initial="30d" />      {/* 'use client' leaf */}
    </Shell>
  );
}

// app/dashboard/RevenueChartData.tsx (Server)
export async function RevenueChartData() {
  const series = await getRevenueSeries();
  return <RevenueChart series={series} />;   // client chart gets plain JSON props
}

// RevenueChart.tsx
'use client';
export function RevenueChart({ series }: { series: Point[] }) { /* tooltips, zoom */ }
```

## Trade-offs & pitfalls
- `'use client'` at the root layout turns the whole app back into a client bundle.
- Passing functions/class instances/Dates-with-methods across the boundary fails or serializes lossy.
- Sequential `await`s in nested Server Components recreate waterfalls on the server; hoist and parallelize, or split with Suspense.
- Importing a server-only module (DB client, secrets) from a client file leaks or breaks the build; use a `server-only` guard package (verify name in your framework).
- Caching semantics differ per framework and have changed across Next.js versions; this area moves fast, check current docs.

## Likely follow-ups
- **RSC vs SSR?** SSR renders components to HTML then hydrates all of them; RSC decides which components exist on the client at all. Complementary.
- **Can a Server Component use state/effects?** No hooks tied to client lifecycle, no browser APIs, no event handlers.
- **When not to adopt?** Highly interactive apps (editors, design tools, consoles): gains are small; a SPA with good splitting and a solid data layer may be simpler.
- **How do you measure success?** JS bytes shipped, LCP, INP, server cost/latency, before vs after per surface.

## Say it in 60 seconds
Server Components run only on the server, can await data directly, and never ship their code; they send a serialized UI tree with slots for Client Components. Client Components are ordinary React that hydrate and handle interaction. The boundary is a module boundary marked by `'use client'`, and only serializable props cross it, so I push that directive down to interactive leaves and pass server trees into client layouts as children. The wins are less JavaScript, data fetched near the source in parallel, and secrets kept server-side. The costs are a new mental model, framework coupling, tricky caching and server round trips for interactions. For a read-heavy dashboard with widget islands it's a good fit; I'd decide per surface and measure bytes, LCP and INP.
