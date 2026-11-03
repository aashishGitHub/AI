# HTTP caching for SPAs: Cache-Control, ETags, immutable assets and the index.html problem
**Round:** 07 · Browser & Web Platform · **Level:** Senior · **Time:** 15 min · **Tags:** http caching · cache-control · etag
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: after a deploy some users see the old SPA for days; others re-download an 800 KB bundle every visit. Design headers for HTML, hashed assets, APIs and the CDN.

## What they're really testing
That you split caching by "does the URL change when content changes?", and that you know the deploy failure modes (stale HTML, deleted chunks).

## Core answer (key points)
- **Two classes of file.**
  - Content-hashed assets (`app.3f9a1c.js`, hashed fonts/images): the URL is the version. Cache forever: `public, max-age=31536000, immutable`.
  - The entry document (`index.html`) and anything with a stable URL: `no-cache` (store it, but revalidate with ETag / Last-Modified every time). A deploy is visible on the next load, and an unchanged page costs only a 304.
- **The two reported bugs map cleanly:**
  - "Old version for days" → `index.html` cached with a `max-age` (or a CDN default TTL, or an old service worker serving the shell).
  - "800 KB every visit" → assets not fingerprinted, or served `no-store`/`no-cache`, or a CDN that varies on cookies so it never hits.
- **ETag alone isn't enough:** it still costs a round trip per resource. With dozens of chunks that's latency on every load; `immutable` + long `max-age` removes the request entirely.
- **APIs:** decide per endpoint. Shared/rarely changing → `public, s-maxage=60, stale-while-revalidate=300` (CDN caches, serves stale while refreshing). Per-user → `private` with short max-age. Sensitive (`/me`, payment) → `no-store`.
- **CDN:** content-hashed files never need purging, only HTML and API. Normalize the cache key (strip tracking query params, don't key on cookies). `Vary: Accept-Encoding` is fine; `Vary: Cookie` kills the hit rate.
- **Debug:** DevTools Network "Size" column (disk/memory cache), response `Age` header and CDN `x-cache`/hit headers, disable cache toggle; `curl -I` to see raw headers.

## Mental model / flow
| Directive | Meaning |
|---|---|
| `max-age=N` | Fresh for N s; no request while fresh |
| `s-maxage=N` | Freshness override for shared caches (CDN) |
| `no-cache` | May store; must revalidate before each use |
| `no-store` | Never store |
| `public` / `private` | Shared caches allowed / browser only |
| `immutable` | Don't revalidate even on user reload |
| `stale-while-revalidate=N` | Serve stale up to N s while fetching fresh in background |
| `ETag` + `If-None-Match` | Conditional request; 304 skips the body |

Stale-chunk failure after deploy:
```
tab open with old index.html in memory
  → deploy, old /assets/*.js deleted
  → user clicks lazy route → import('./settings.ab12.js') → 404 → ChunkLoadError → blank/broken route
```

## Code sketch
```ts
// Lazy import wrapper: one guarded hard reload on chunk failure.
export function lazyWithReload<T>(load: () => Promise<T>): () => Promise<T> {
  return async () => {
    try {
      const mod = await load();
      sessionStorage.removeItem('chunk-reload');
      return mod;
    } catch (err) {
      if (!sessionStorage.getItem('chunk-reload')) {
        sessionStorage.setItem('chunk-reload', '1');
        location.reload();
      }
      throw err;
    }
  };
}
```

## Trade-offs & pitfalls
- Wiping the bucket on every deploy guarantees ChunkLoadErrors for open tabs. Keep old assets for N days (or N releases) and expire them later.
- Reload-on-error needs a loop guard (sessionStorage flag), otherwise a genuinely missing chunk reloads forever.
- A version check (poll `/version.json` or read a build header) with a "new version, reload" toast is friendlier than surprise reloads, especially on forms.
- Service workers help (controlled updates) and hurt (an old SW can serve an old shell indefinitely). See the SW question.
- `no-store` on the document can make the page ineligible for the back/forward cache in some browsers; prefer `no-cache` for HTML.
- `immutable` is honored by Firefox and Safari; Chrome mostly skips revalidation on reload for long max-age anyway. I'm not certain of current per-browser details; verify in MDN if asked.

## Likely follow-ups
- **Why not `max-age=0` for HTML?** `max-age=0, must-revalidate` behaves roughly like `no-cache`; both revalidate. `no-store` is overkill and can cost bfcache.
- **Where does bfcache fit?** It keeps the whole page in memory for instant back/forward. `no-store` on the document and `unload` handlers can block it.
- **How do you invalidate on deploy?** You don't for hashed assets; purge only HTML (and selected API paths) at the CDN as the last deploy step.
- **Last-Modified vs ETag?** Both enable conditional requests; ETag is content-based and more precise, Last-Modified has 1 s granularity and breaks across servers with different mtimes.
- **What about `stale-if-error`?** Lets a cache serve stale content if origin errors; useful resilience for API/CDN.

## Say it in 60 seconds
I fingerprint every build asset and serve it as `public, max-age=31536000, immutable`, so the browser and CDN never ask again; a new build means new URLs. The HTML entry point gets `no-cache` with an ETag, so it's stored but revalidated on each load, which picks up a deploy immediately and costs just a 304 otherwise. APIs are per endpoint: `s-maxage` plus `stale-while-revalidate` for shared data, `private` or `no-store` for user data. "Old version for days" is almost always a cached index.html or an old service worker; "full download every time" is missing hashes or a CDN keyed on cookies. Finally I handle the deploy race: keep old chunks around for a while, catch chunk-load errors with a one-time guarded reload, and optionally show a "new version available" prompt.
