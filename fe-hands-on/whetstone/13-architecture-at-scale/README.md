# 13 · Architecture at Scale
> Lead/principal system-level frontend decisions: composition, repo structure, migrations, rendering, state ownership, platform governance, APIs, telemetry and release control · 9 questions · ~2 h 25 min
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Micro-frontends and Module Federation: when do they pay off, and how do they fail? | Principal | 20 min | micro-frontends · module federation · architecture | [notes](01-micro-frontends-module-federation-tradeoffs.md) |
| 02 | Monorepos for frontend: pnpm workspaces, Nx or Turborepo, boundaries and CI caching | Lead / Staff | 15 min | monorepo · pnpm · nx | [notes](02-frontend-monorepo-tooling-boundaries.md) |
| 03 | Lead an incremental migration (for example AngularJS to React) without a rewrite freeze | Principal | 20 min | migration · strangler fig · angularjs | [notes](03-incremental-migration-strangler-fig.md) |
| 04 | Choose a rendering architecture: SPA, SSR, SSG/ISR, streaming, islands or React Server Components | Lead / Staff | 18 min | rendering · ssr · ssg | [notes](04-choose-rendering-architecture-per-surface.md) |
| 05 | State architecture: server state, client state, URL state and form state. Who owns what? | Lead / Staff | 15 min | state management · react query · redux | [notes](05-state-architecture-ownership-by-kind.md) |
| 06 | Run a design system as a product: versioning, contribution, adoption and breaking changes | Principal | 15 min | design systems · governance · versioning | [notes](06-design-system-as-a-product.md) |
| 07 | API layer choices: REST vs GraphQL vs tRPC, Backend-for-Frontend, and generated clients | Lead / Staff | 15 min | api design · rest · graphql | [notes](07-api-layer-rest-graphql-trpc-bff.md) |
| 08 | Frontend observability: errors, RUM, tracing, source maps and alerting people trust | Lead / Staff | 15 min | observability · rum · error tracking | [notes](08-frontend-observability-rum-alerting.md) |
| 09 | Feature flags and progressive delivery: kill switches, flag debt and testing | Lead / Staff | 12 min | feature flags · progressive delivery · canary | [notes](09-feature-flags-progressive-delivery.md) |

## How these connect
- **Org shape drives architecture (Conway's law):** study 01 (micro-frontends) and 02 (monorepo) together; the usual answer is "modular monorepo first, federate only where independent deploy pays".
- **Migrations reuse the same toolkit:** 03 (strangler fig) leans on 01's bridges, 02's boundaries and 09's flags for per-route cutover.
- **Data flow trio:** 04 (where HTML is rendered), 05 (who owns each kind of state) and 07 (how data reaches the client, BFF) form one story from server to component.
- **Platform governance:** 06 (design system) and 02 share the same mechanics: semver/changesets, codemods, lint-enforced rules, adoption metrics.
- **Safe delivery loop:** 09 (flags, canary) only works with 08 (release-tagged telemetry and auto-rollback); always pair them.
- **Suggested order:** 05 -> 04 -> 07 -> 02 -> 01 -> 03 -> 06 -> 08 -> 09.
