# Images and fonts: responsive images, formats, lazy loading, font-display and layout shift
**Round:** 08 · Performance · **Level:** Senior · **Time:** 12 min · **Tags:** images · fonts · avif
Source: https://whetstone-v1.vercel.app/#performance

Scenario: marketing page ships 6 MB of images, shifts when fonts load, and the hero image is the LCP element.

## What they're really testing
Fluency in the responsive image primitives (`srcset`/`sizes`/`<picture>`), loading priority, and font loading that doesn't cause CLS. Plus a checklist you'd enforce.

## Core answer (key points)
- **Formats:** AVIF first, WebP fallback, JPEG/PNG last via `<picture>`/`<source type>`. Typical savings are large vs JPEG (approximate; depends on content). An image CDN can negotiate via `Accept` header automatically.
- **Size:** `srcset` with width descriptors + an accurate `sizes` so the browser picks the right candidate before layout. Without `sizes` it assumes `100vw` and overfetches on desktop grids.
- **Dimensions:** always `width`/`height` attributes (browser derives aspect ratio) or CSS `aspect-ratio` on the container. Prevents CLS.
- **Loading:** `loading="lazy"` + `decoding="async"` below the fold; hero gets `fetchpriority="high"` and is eager and in the HTML.
- **Fonts:**
  - Self-host WOFF2, subset with `unicode-range`, use a variable font instead of many weights.
  - Preload only the 1-2 faces used above the fold (`crossorigin` required).
  - `font-display: swap` shows fallback then swaps (risk: reflow); `optional` uses the web font only if it's ready almost immediately (no swap shift, may show fallback on first visit).
  - Kill the swap shift with a **metric-matched fallback**: `@font-face` on a local font with `size-adjust`, `ascent-override`, `descent-override`, `line-gap-override`. Tools (fontaine, `next/font`, Capsize) compute values.
- **Checklist:** no lazy above the fold; lazy everything else; dimensions on every media; no base64 big images in CSS/JS; SVG icons (inline or sprite), not icon fonts; video with `preload="none"`/`metadata` + poster, no autoplaying large video on mobile.

## Mental model / flow
```
Browser picks image:  sizes (layout width guess) × DPR → choose smallest srcset candidate ≥ that
<picture>: first <source> whose type is supported wins, then srcset/sizes inside it

Font timeline (swap):  fallback text ──► web font arrives ──► swap (reflow unless metrics match)
Font timeline (optional): ~100ms block ──► font ready? use it : keep fallback for this page
```

## Code sketch
```html
<picture>
  <source type="image/avif" srcset="/m/hero-640.avif 640w, /m/hero-1280.avif 1280w, /m/hero-1920.avif 1920w">
  <source type="image/webp" srcset="/m/hero-640.webp 640w, /m/hero-1280.webp 1280w, /m/hero-1920.webp 1920w">
  <img src="/m/hero-1280.jpg"
       srcset="/m/hero-640.jpg 640w, /m/hero-1280.jpg 1280w, /m/hero-1920.jpg 1920w"
       sizes="100vw" width="1920" height="900"
       fetchpriority="high" alt="Team collaborating around a whiteboard">
</picture>

<img src="/m/card-400.webp" srcset="/m/card-400.webp 400w, /m/card-800.webp 800w"
     sizes="(min-width: 1024px) 33vw, 100vw" width="800" height="600"
     loading="lazy" decoding="async" alt="">
```
```css
@font-face {
  font-family: 'Display';
  src: url('/fonts/display-var.woff2') format('woff2');
  font-weight: 400 800;
  font-display: swap;
  unicode-range: U+0000-00FF;
}
@font-face {
  font-family: 'Display Fallback';
  src: local('Arial');
  size-adjust: 103%;
  ascent-override: 90%;
  descent-override: 22%;
}
h1, body { font-family: 'Display', 'Display Fallback', system-ui, sans-serif; }
```
(Override percentages above are placeholders; compute real ones per font.)

## Trade-offs & pitfalls
- `sizes` that lie (e.g. `100vw` for a 300 px card) waste bytes; keep them in sync with CSS breakpoints.
- AVIF encode is slow; do it at build time or via an image CDN, not on request without caching.
- Preloading a responsive image needs `imagesrcset`/`imagesizes`, otherwise you can fetch two variants.
- `font-display: optional` can mean brand font never shows on slow first visits; acceptable for body text, debatable for logos/headlines.
- Lazy-loading via JS/IntersectionObserver libraries hides images from the preload scanner; prefer native `loading`.
- Decorative images should have `alt=""`; content images need real alt text (a11y, not perf, but reviewers check).

## Likely follow-ups
- **x vs w descriptors?** `x` for fixed-size images at different DPRs; `w` + `sizes` for fluid layout.
- **When to use `<picture>` vs just `srcset`?** `<picture>` for format fallback or art direction (different crop per breakpoint).
- **How do you enforce this?** Lint (eslint-plugin-jsx-a11y, framework image component required), Lighthouse CI image audits, CI check on image byte budget.
- **Why not icon fonts?** Render as text (a11y noise, FOIT), blocky anti-aliasing, all-or-nothing download.
- **What does `decoding="async"` do?** Hints that decode can happen off the critical path so it doesn't delay other content; effect varies by browser.

## Say it in 60 seconds
For images I serve AVIF with WebP and JPEG fallbacks, sized to what's actually displayed using srcset with width descriptors and an accurate sizes attribute, so the browser picks the right file before layout. Every image gets width and height so space is reserved and nothing shifts. Below the fold is natively lazy; the hero is eager, in the HTML, and fetchpriority high because it's the LCP element. For fonts I self-host subsetted WOFF2, ideally one variable font, preload only the one or two faces used up top with crossorigin, and choose font-display deliberately: swap with a fallback whose metrics are matched using size-adjust and ascent overrides so the swap doesn't reflow, or optional where stability matters most. Then I enforce it with an image component, lint rules and Lighthouse CI.
