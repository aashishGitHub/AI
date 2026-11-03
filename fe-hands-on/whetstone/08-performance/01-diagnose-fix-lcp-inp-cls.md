# Diagnose and fix LCP, INP and CLS on a real page
**Round:** 08 · Performance · **Level:** Senior · **Time:** 20 min · **Tags:** core web vitals · lcp · inp
Source: https://whetstone-v1.vercel.app/#performance

Scenario: mobile field data for a product page shows LCP 4.8 s, INP 420 ms, CLS 0.31. One week. How do you diagnose each and what goes first?

## What they're really testing
A method, not a bag of tricks: start from field p75, decompose each metric into sub-parts, fix the largest sub-part, verify in the field, and guard against regressions.

## Core answer (key points)
- **Targets (p75, "good"):** LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1. All three are well into "poor" here.
- **Start from field data** (CrUX, own RUM) at the 75th percentile, segmented by route, device class, connection. Lab tools are for reproduction, not truth.
- **LCP = TTFB + resource load delay + resource load duration + element render delay.** Find which part dominates:
  - TTFB → CDN/edge caching of HTML, SSR caching, kill redirects, faster backend.
  - Load delay (image discovered late) → LCP image in server HTML, `fetchpriority="high"`, no `loading="lazy"`, preload if it's a CSS background.
  - Load duration → right size + AVIF/WebP + `srcset`/`sizes`, image CDN.
  - Render delay → less blocking CSS/JS, SSR/SSG the hero instead of client-render, inline critical CSS, remove A/B-test anti-flicker snippets that hide the page.
- **INP = input delay + processing + presentation delay.** Fixes: break up long tasks and yield, paint the urgent feedback first, shrink React re-render scope (colocate state, transitions, virtualization), defer analytics, move CPU work to workers, cut third-party main-thread time.
- **CLS = sum of unexpected shifts (session windows).** Fixes: `width`/`height` or `aspect-ratio` on images, video, iframes, ad slots; never inject banners above content (overlay or reserve); font fallbacks with matched metrics or `font-display: optional`; skeletons with final dimensions; animate `transform`.
- **One-week plan:** day 1 instrument with `web-vitals/attribution` and identify the LCP element, the slowest interactions, and the shifting nodes. Then fix in payoff order (usually LCP image discovery/priority and CLS reservations are quick wins; INP takes longer). Ship behind measurement, compare p75 per release.

## Mental model / flow
```
LCP: |-- TTFB --|-- load delay --|-- load duration --|-- render delay --|
          server     discovered late?    bytes too big?     blocked by JS/CSS/font?

INP: click ─► [input delay: main thread busy] ─► [handlers run] ─► [render + paint] ─► next frame

CLS: element moves without user input → score = impact fraction × distance fraction, summed per window
```

## Code sketch
```ts
import { onLCP, onINP, onCLS, type Metric } from 'web-vitals/attribution';

function report(metric: Metric) {
  const body = JSON.stringify({
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    id: metric.id,
    route: location.pathname,
    release: import.meta.env.VITE_RELEASE,
    attribution: metric.attribution, // LCP element/sub-parts, INP target + LoAF scripts, CLS largest shift source
  });
  navigator.sendBeacon('/rum', body);
}

onLCP(report);
onINP(report);
onCLS(report);
```

## Trade-offs & pitfalls
- Lighthouse runs one synthetic load and can't measure INP (no real interactions; TBT is a lab proxy). Expect lab/field disagreement.
- Mean hides the tail; look at p75 and the distribution.
- SSR usually helps render delay but can raise TTFB if the server is slow; stream and cache.
- CLS fixes that use skeletons can *add* shift if the skeleton height differs from final content.
- Shipping many fixes at once makes attribution impossible; annotate releases.
- Field data lags: CrUX is a 28-day rolling window, so your own RUM is needed to confirm within the week.

## Likely follow-ups
- **LCP good in Lighthouse, poor in CrUX?** Real users: slower devices/networks, cold caches, heavier logged-in content, geography, A/B tools hiding content.
- **Does SSR always improve LCP?** No; it trades render delay for TTFB. Measure both sub-parts.
- **What counts as an LCP candidate?** Images, poster images, background images via `url()`, block-level text; the largest in viewport until first input/scroll.
- **What resets CLS?** Shifts within 500 ms of user input are excluded; CLS reports the worst 5 s session window (gaps < 1 s).
- **How do you prevent regression?** Lighthouse CI + size budgets per PR, RUM alerts on p75 per route after each release.

## Say it in 60 seconds
I start from field data at p75, by route and device, and break each metric into its parts. LCP is TTFB plus load delay plus load duration plus render delay; at 4.8 seconds it's usually a late-discovered or lazy hero image, an oversized image, or client-side rendering, so I put the image in the server HTML with fetchpriority high, right-size it in AVIF, and cut blocking JS and CSS. INP at 420 milliseconds means long tasks around interactions; I find them with web-vitals attribution and Long Animation Frames, paint the urgent feedback first, yield, shrink re-renders and defer analytics. CLS of 0.31 is missing dimensions, late-inserted banners or font swaps, so I reserve space and use metric-matched fallbacks. I verify each fix in RUM per release and lock it in with CI budgets.
