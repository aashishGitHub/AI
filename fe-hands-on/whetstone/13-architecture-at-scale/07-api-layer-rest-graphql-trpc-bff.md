# API layer choices: REST vs GraphQL vs tRPC, Backend-for-Frontend, and generated clients
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** api design · rest · graphql
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: each screen calls 6 REST endpoints and mobile over-fetches. Compare options and pick one.

## What they're really testing
Whether you weigh protocol choice against team structure and operational cost, and recognize that a BFF often solves the actual problem regardless of protocol.

## Core answer (key points)
- **REST (+OpenAPI):** simple, universal, natural HTTP/CDN caching on GET. Weakness: chatty screens, over/under-fetching.
- **GraphQL:** one round trip with exactly the fields a screen needs, typed schema, rich clients. Cost: resolvers and N+1 (needs dataloaders), query cost limits, harder HTTP caching (mitigated by persisted queries), normalized client cache.
- **tRPC:** end-to-end TS types inferred with almost no ceremony. Cost: client and server must share one TS codebase; poor fit for multiple client languages or public APIs.
- **BFF (backend-for-frontend):** a thin service owned by the UI team that aggregates and shapes upstream APIs per client. Often the highest-leverage fix for "6 calls per screen" and mobile over-fetch, and it can use any protocol.
- **Always generate typed clients** from the schema (OpenAPI codegen, GraphQL codegen) and add contract tests or schema-diff checks in CI.
- **For the scenario:** add a BFF exposing screen-shaped endpoints (or GraphQL at the BFF if many screens have varied shapes), keep upstream REST as is, migrate screen by screen.

## Mental model / flow
```
Before: Screen -> 6x REST (auth, user, orders, prefs, flags, counts)
After:  Screen -> BFF /screens/orders-overview (1 call, mobile-trimmed)
                   BFF -> upstream services in parallel, server-side token handling, caching
```

## Code sketch
```ts
// Own sketch: BFF route that composes upstreams in parallel and shapes for the UI
app.get('/bff/orders-overview', async (req, res) => {
  const ctx = authContext(req);
  const [user, orders, counts] = await Promise.all([
    users.get(ctx), orders.list(ctx, { limit: 20 }), stats.counts(ctx),
  ]);
  res.json({
    user: { id: user.id, name: user.displayName },
    orders: orders.items.map(o => ({ id: o.id, total: o.total, status: o.status })),
    badges: { open: counts.open },
    nextCursor: orders.nextCursor,
  });
});
```

## Trade-offs & pitfalls
| | REST+OpenAPI | GraphQL | tRPC |
|---|---|---|---|
| Typing | codegen | codegen per operation | inferred |
| Over/under-fetch | common | solved | per procedure |
| HTTP caching | natural | harder (persisted queries help) | possible for queries |
| Server complexity | low | higher | low |
| Multi-language clients | easy | easy | no |
- BFF risk: business logic creeping in and duplicating services. Keep it to composition and presentation.
- GraphQL without cost limits or persisted queries is a DoS and security surface.
- Inconsistent error envelopes and pagination styles across endpoints hurt the client more than protocol choice. Standardize: `{code, message, fieldErrors}`, cursor pagination, partial-success rules.

## Likely follow-ups
- **Fragment colocation?** Each component declares its data needs as a fragment; parents compose them (Relay pattern), so data deps move with components.
- **Versioning?** REST: additive changes + deprecation headers; GraphQL: deprecate fields, track usage, remove when zero.
- **Who owns the BFF on-call?** The UI team; that's the price of autonomy, needs basic SRE practices.
- **Contract testing?** Consumer-driven contracts (e.g. Pact) or OpenAPI/GraphQL schema diff in CI.

## Say it in 60 seconds
REST is simple and caches well but screens get chatty; GraphQL fetches exactly what a screen needs in one trip with a typed schema, at the cost of resolver complexity, N+1 and cost controls; tRPC gives effortless end-to-end types but only inside one TypeScript codebase. For six calls per screen and mobile over-fetch, I'd introduce a backend-for-frontend owned by the UI team that aggregates upstream calls and shapes responses per client, which solves the problem regardless of protocol. Either way, I'd generate typed clients from the schema, standardize errors and pagination, and gate changes with contract tests in CI.
