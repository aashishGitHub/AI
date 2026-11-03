# 07 · Browser & Web Platform
> What the browser does with your bytes: render pipeline, HTTP caching, CORS, load priority, service workers, storage and workers · 7 questions · ~1 h 39 min
Source: https://whetstone-v1.vercel.app/#browser-platform

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | The critical rendering path: parse, style, layout, paint, composite. What triggers what? | Senior | 15 min | rendering · layout · paint | [notes](01-critical-rendering-path-what-triggers.md) |
| 02 | HTTP caching for SPAs: Cache-Control, ETags, immutable assets and the index.html problem | Senior | 15 min | http caching · cache-control · etag | [notes](02-http-caching-for-spas.md) |
| 03 | CORS end to end: simple vs preflighted requests, credentials and common misconfigurations | Senior | 12 min | cors · preflight · credentials | [notes](03-cors-end-to-end.md) |
| 04 | Preload, preconnect, modulepreload, fetchpriority: how do you load the right thing first? | Lead / Staff | 12 min | preload · preconnect · fetchpriority | [notes](04-preload-preconnect-fetchpriority.md) |
| 05 | Service workers: caching strategies, the update lifecycle, and the bugs they cause | Lead / Staff | 18 min | service worker · pwa · offline | [notes](05-service-workers-strategies-lifecycle-bugs.md) |
| 06 | Choosing client storage: cookies, localStorage, IndexedDB, OPFS, Cache API, and syncing across tabs | Senior | 12 min | storage · indexeddb · localstorage | [notes](06-choosing-client-storage-cross-tab.md) |
| 07 | When and how do you move work off the main thread with Web Workers? | Lead / Staff | 15 min | web workers · comlink · transferables | [notes](07-web-workers-off-main-thread.md) |

## How these connect
- **Load path (01 → 04):** 01 explains what blocks first paint; 04 is the toolkit for reordering the network so the LCP resource wins. Study together, then jump to round 08 Q on LCP/INP/CLS.
- **Deploy/update path (02 → 05):** same root bug in both, a stale `index.html` or shell pointing at deleted chunks. 02 fixes it with headers; 05 adds a second cache layer that can make it worse. Learn the `no-cache` HTML + `immutable` hashed assets rule first.
- **Origin boundaries (03, 06):** CORS controls cross-origin reads; storage is partitioned by origin. Both feed into the security round (cookies, SameSite, XSS reading localStorage).
- **Main-thread budget (01, 07):** layout thrashing and long JS tasks both starve input. 07 is the "move it elsewhere" answer; 01 is the "do less rendering work" answer.
- **Suggested order:** 01 → 04 → 02 → 05 → 06 → 03 → 07.
