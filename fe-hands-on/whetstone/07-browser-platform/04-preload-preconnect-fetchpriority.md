# Preload, preconnect, modulepreload, fetchpriority: how do you load the right thing first?
**Round:** 07 · Browser & Web Platform · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** preload · preconnect · fetchpriority
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: product page with an LCP hero image, a web font, third-party analytics, and a lazy carousel. Lighthouse says the LCP image starts late. Decide the hints.

## What they're really testing
Knowing the browser's default prioritization and where it is blind, choosing a minimal set of hints, and proving the effect with data instead of cargo-culting.

## Core answer (key points)
- **Defaults:** priority comes from resource type + position + discovery time. CSS in head = highest; sync scripts high; images start low and get bumped once found in viewport (after layout); fonts are only requested once CSS shows they're used.
- **Blind spots you fix:** late discovery (font behind CSS, CSS background image, image rendered by JS), wrong priority (hero image treated as generic image), connection setup to third-party origins.
- **Per resource in the scenario:**
  - **Hero image:** a real `<img>` in the HTML (not JS-rendered, not CSS background) with `fetchpriority="high"`, `width`/`height`, responsive `srcset`/`sizes`, never `loading="lazy"`. If it must be a background image, `preload as="image"` (with `imagesrcset` if responsive).
  - **Web font:** `preload as="font" type="font/woff2" crossorigin` for the one critical weight; `font-display: swap`/`optional`.
  - **Image CDN on another origin:** `preconnect` (with `crossorigin` if fetched in CORS mode).
  - **Analytics:** no hint; load with `defer`/after load, maybe `fetchpriority="low"`. Remove any existing preconnect for it.
  - **Carousel:** lazy-load below-the-fold slides, `fetchpriority="low"` on non-first slides.
  - **Next route JS:** `modulepreload` for the chunk definitely needed soon (fetches + parses the module graph node); `prefetch` for likely-next navigation (idle, lowest priority, into HTTP cache).
- **Verify:** DevTools Network with the Priority column and waterfall; WebPageTest filmstrip; Lighthouse "Preload LCP image" / "Preconnect" audits; in the field, the LCP sub-parts (TTFB, resource load delay, resource load duration, element render delay) from CrUX/RUM.

## Mental model / flow
```
Hint            What it does                           Use for
preconnect      DNS + TCP + TLS now                    2-4 critical 3P origins
dns-prefetch    DNS only (cheap)                       the long tail of origins
preload         fetch now, don't execute, high prio    late-discovered critical asset
modulepreload   fetch + parse ES module (+deps opt.)   next-needed JS chunk
prefetch        low-prio fetch for future nav          likely next page/chunk
fetchpriority   nudge high/low within the type         LCP img high; carousel low
speculationrules prefetch/prerender whole pages (Chromium) MPA next-page instant nav
```
LCP fix order: discoverable (in HTML) → prioritized (`fetchpriority=high`) → small (AVIF/WebP, right size) → fast origin (preconnect / same origin).

## Code sketch
```html
<link rel="preconnect" href="https://img.shopcdn.example" crossorigin>
<link rel="preload" href="/fonts/brand-var.woff2" as="font" type="font/woff2" crossorigin>

<img src="/p/hero-1200.avif"
     srcset="/p/hero-640.avif 640w, /p/hero-1200.avif 1200w"
     sizes="(max-width: 700px) 100vw, 1200px"
     width="1200" height="675" fetchpriority="high" alt="Trail running shoe, side view">

<link rel="modulepreload" href="/assets/cart.7c1d.js">
<script src="https://analytics.example/a.js" defer></script>
```

## Trade-offs & pitfalls
- **Over-hinting:** everything high means nothing is. Preloads steal bandwidth from render-critical CSS. Unused preloads produce console warnings after a few seconds.
- **Font preload without `crossorigin`:** fonts are fetched in CORS mode, so a non-CORS preload doesn't match and the font downloads twice.
- **`loading="lazy"` on the LCP image:** delays it until layout; a common framework default to watch for.
- **Too many preconnects:** each socket + TLS handshake costs CPU and can contend; unused ones are closed after ~10 s (approximate, verify).
- **Preloading the wrong responsive candidate:** a plain `preload href` ignores `srcset`; use `imagesrcset`/`imagesizes` or you fetch two images.
- **Speculation Rules** are Chromium-only and prerender runs page JS (analytics double counting, state mutations); use `prefetch` or moderate eagerness first.
- In SPAs, prefetch route chunks and data on intent (hover, focus, viewport) rather than at load.

## Likely follow-ups
- **preload vs prefetch?** Preload = needed for this page, now, high priority. Prefetch = maybe needed for a future navigation, idle, low priority.
- **How does `fetchpriority` interact with HTTP/2?** It changes the browser's priority signal on the stream; the server/CDN has to honor priorities for it to matter (some CDNs historically didn't).
- **Early Hints (103)?** Server sends `Link: preload/preconnect` headers before the final response, so hints start during server think time.
- **How do you stop regressions?** Lighthouse CI budgets on LCP and a check that the LCP element isn't lazy and has `fetchpriority`.
- **Why not inline the hero image as base64?** Bloats HTML, blocks HTML parse/compression benefits, not cacheable separately.

## Say it in 60 seconds
The browser prioritizes by type, position and when it discovers a resource, so my job is to fix its blind spots, using as few hints as possible. For this page: make the hero a real `<img>` in the HTML with `fetchpriority="high"`, proper dimensions and responsive sources, and definitely not lazy. Preload just the one critical font with `crossorigin`. Preconnect to the image CDN. Leave analytics un-hinted and deferred, lazy-load the carousel and mark its extra slides low priority. Modulepreload the next route chunk only if it's certainly needed, otherwise prefetch on intent. Then I verify in the waterfall's Priority column and watch the LCP breakdown, especially resource load delay, in field data, because every hint competes for bandwidth and over-hinting makes things worse.
