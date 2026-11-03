# Service workers: caching strategies, the update lifecycle, and the bugs they cause
**Round:** 07 · Browser & Web Platform · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** service worker · pwa · offline
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: adding offline support to a news PWA. After release some users are stuck on an old version; one user gets a blank page after a deploy. Design the strategy and update flow.

## What they're really testing
Strategy-per-resource reasoning, a precise understanding of the install/waiting/activate lifecycle, and operational maturity (kill switch, cache hygiene).

## Core answer (key points)
- **What it is:** an event-driven script, separate from pages, that intercepts `fetch` for its scope. It's a programmable proxy plus a cache, with no DOM and no guaranteed lifetime.
- **Strategy per resource:**
  - Hashed static assets → **precache** at install, serve **cache-first**.
  - HTML navigations → **network-first** with a short timeout, fall back to cached shell/offline page.
  - Article lists / catalog API → **stale-while-revalidate** (instant, refreshed in background).
  - Images → **cache-first** with expiration (max entries/age).
  - Auth/personal API → **network-only** (or carefully scoped cache cleared on logout).
- **Lifecycle:** `register` → `install` (precache) → **waiting** while any client is still controlled by the old SW → `activate` (delete old caches) → controls subsequent navigations.
  - The waiting phase is why users are "stuck": a new SW won't take over until every tab using the old one is closed. A refresh doesn't do it if the tab is the only client (navigation overlaps).
  - `skipWaiting()` activates immediately, but already-open pages built against old chunks are now served by a SW whose precache has the new ones: mixed versions → the blank page.
  - `clients.claim()` makes the active SW control open pages without reload.
- **Safe update flow:** detect a waiting worker, show "New version, reload?", on accept `postMessage('SKIP_WAITING')`, then reload on `controllerchange`. User-controlled, single reload, consistent version.
- **Plan for the bugs:** never HTTP-cache `sw.js` itself; bound cache growth; avoid opaque responses; clear user caches on logout; ship a **kill-switch** SW.

## Mental model / flow
```
v1 active, controls tabs A,B
deploy v2 ─► browser fetches sw.js (byte-diff) ─► v2 install (precache v2 assets)
                                                    │
                     tabs A,B still on v1 ◄─────────┤ v2 WAITING
                                                    │
         user clicks "Reload" → SKIP_WAITING ───────► v2 activate (delete v1 caches)
                                                    │
                     controllerchange ─► location.reload() ─► tabs on v2
```

## Code sketch
```ts
// sw.ts – hand-rolled shapes; Workbox gives the same with precacheAndRoute + strategies.
const VERSION = 'v42';
const ASSETS = self.__MANIFEST as string[];

self.addEventListener('install', (e: ExtendableEvent) => {
  e.waitUntil(caches.open(`assets-${VERSION}`).then((c) => c.addAll(ASSETS)));
});

self.addEventListener('activate', (e: ExtendableEvent) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k))),
    ),
  );
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});
```
```ts
// app.ts
const reg = await navigator.serviceWorker.register('/sw.js');
const offer = (w: ServiceWorker) => showToast('Update ready', () => w.postMessage('SKIP_WAITING'));
if (reg.waiting) offer(reg.waiting);
reg.addEventListener('updatefound', () => {
  const w = reg.installing!;
  w.addEventListener('statechange', () => {
    if (w.state === 'installed' && navigator.serviceWorker.controller) offer(w);
  });
});
let reloaded = false;
navigator.serviceWorker.addEventListener('controllerchange', () => {
  if (!reloaded) { reloaded = true; location.reload(); }
});
```
```ts
// kill-switch sw.js, deployable in minutes
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', async () => {
  for (const k of await caches.keys()) await caches.delete(k);
  await self.registration.unregister();
  for (const c of await self.clients.matchAll()) (c as WindowClient).navigate(c.url);
});
```

## Trade-offs & pitfalls
- **Caching `sw.js` via HTTP:** browsers cap SW script HTTP caching at 24h and check on navigation, but still serve it `no-cache` so updates are seen promptly.
- **Precaching `index.html` cache-first:** pins the old shell forever; use network-first for navigations.
- **User data in caches** survives logout and can leak on shared devices; partition by user or clear on logout.
- **Opaque (no-cors) responses:** can't inspect status (you may cache a 500), and browsers pad their quota cost heavily (Chromium ~7 MB each, approximate).
- **Cache growth/eviction:** set expiration; check `navigator.storage.estimate()`.
- **Dev confusion:** stale SW in development; don't register in dev, or use DevTools "Update on reload".
- **Navigation preload** avoids SW boot time delaying network-first navigations; worth enabling.

## Likely follow-ups
- **How often does the browser check for an update?** On navigation into scope and functional events, throttled; at least every 24h effectively. `reg.update()` forces a check.
- **What triggers an update?** Byte difference in `sw.js` (and in `importScripts` dependencies in modern browsers).
- **Why not always `skipWaiting` + `clients.claim`?** Fine only if old pages can run against new assets; otherwise mixed versions and chunk 404s.
- **Offline writes?** Queue in IndexedDB and replay (Background Sync in Chromium, or replay on next online event).
- **How do you test it?** Workbox unit tests for routes, Playwright with `context.setOffline(true)`, and an e2e that deploys v1 then v2 and asserts the update toast.

## Say it in 60 seconds
A service worker is a programmable proxy that sits between the page and the network. I pick a strategy per resource: precache hashed assets and serve cache-first, network-first with a timeout for HTML so a deploy shows up, stale-while-revalidate for article lists, cache-first with expiry for images, and network-only for personal data. The "stuck on old version" bug is the lifecycle: a new worker installs and then waits until every tab on the old one closes. The blank page is usually the opposite mistake, skipWaiting forcing a new worker under pages built for the old assets. So I make updates explicit: detect the waiting worker, show a reload prompt, skip waiting on accept and reload once on controllerchange. I serve sw.js no-cache, bound and version caches, clear them on logout, and keep a kill-switch worker ready to unregister and wipe caches.
