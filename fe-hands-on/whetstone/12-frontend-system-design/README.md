# 12 · Frontend System Design
> A repeatable 45-minute framework (RADIO), then seven full client-side designs: feed, product page, live dashboard, spreadsheet, collaborative editor, offline-first app, autocomplete · 8 questions · ~3 h 27 min
Source: https://whetstone-v1.vercel.app/#frontend-system-design

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | A framework for frontend system design interviews, and how to spend the 45 minutes | Senior | 12 min | system design · interview framework · radio | [notes](01-radio-framework-45-minutes.md) |
| 02 | Design a news feed (Twitter/LinkedIn-style): rendering, pagination, real-time inserts and media | Lead / Staff | 30 min | system design · news feed · pagination | [notes](02-design-news-feed.md) |
| 03 | Design an e-commerce product page: SSR/streaming, caching, SEO, personalization and Core Web Vitals | Lead / Staff | 25 min | system design · e-commerce · ssr | [notes](03-design-ecommerce-product-page.md) |
| 04 | Design a real-time analytics dashboard (Datadog/Grafana-like): data flow, charts and backpressure | Lead / Staff | 30 min | system design · dashboards · real-time | [notes](04-design-realtime-analytics-dashboard.md) |
| 05 | Design a spreadsheet (Google Sheets lite): grid virtualization, formulas and collaboration | Principal | 35 min | system design · spreadsheet · virtualization | [notes](05-design-spreadsheet-sheets-lite.md) |
| 06 | Design a collaborative document editor: OT vs CRDT, presence, offline and undo | Principal | 30 min | system design · collaboration · crdt | [notes](06-design-collaborative-document-editor.md) |
| 07 | Design an offline-first app: local database, sync queue, conflicts and service worker | Lead / Staff | 25 min | system design · offline-first · sync | [notes](07-design-offline-first-app.md) |
| 08 | Design search with autocomplete at scale (frontend side): caching, ranking display and latency | Senior | 20 min | system design · search · autocomplete | [notes](08-design-search-autocomplete.md) |

## How these connect
- 01 is the template; every other note follows its R → A → D → I → O shape. Drill 01 until the time split is automatic.
- **Read-heavy, render-bound:** 02 (feed) and 03 (product page) are about rendering strategy, caching tiers, and Core Web Vitals. Study together: cacheability split (03) + normalized cache and virtualization (02).
- **Stream-heavy, update-bound:** 04 (dashboard) is backpressure and canvas; 08 (autocomplete) is request racing and caching at keystroke rate. Both are "events arrive faster than you should render".
- **Write-heavy, consistency-bound:** 05 (spreadsheet), 06 (editor), 07 (offline-first) share operations, ordering, conflict resolution and per-user undo. Do 07 → 06 → 05 (ascending difficulty).
- Recurring building blocks to reuse across answers: normalized client store, URL as state, optimistic update + rollback, virtualization, worker offload, per-widget error boundaries, idempotency keys.
- Suggested order: 01 → 08 → 02 → 03 → 04 → 07 → 06 → 05.
