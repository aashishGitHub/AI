# Design an e-commerce product page: SSR/streaming, caching, SEO, personalization and Core Web Vitals
**Round:** 12 · Frontend System Design · **Level:** Lead / Staff · **Time:** 25 min · **Tags:** system design · e-commerce · ssr
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: high-traffic PDP; SEO-critical; personalized price/stock; heavy images; strict LCP target.

## What they're really testing
Can you slice one page by freshness/cacheability and map each slice to a rendering and caching strategy, while protecting LCP, SEO and the buy path?

## Core answer (key points)
- **Requirements:** gallery, variants, price + availability, add to cart, reviews, recommendations, breadcrumbs, shareable variant URLs. NFRs: LCP < 2.5s on mid mobile (the "good" CWV threshold), indexable, flash-sale spikes, A/B testing, multi-region, a11y, localized prices.
- **Split by cacheability (the core idea):**

| Region | Freshness | Strategy |
|---|---|---|
| Title, images, description, specs | hours | SSG/ISR or edge cache; tag-based purge |
| Price, stock, promo | seconds-minutes | request-time fetch, streamed; or client fetch with sized skeleton |
| Add to cart | interactive | small hydrated island |
| Reviews | minutes | streamed behind Suspense, paginated |
| Recs, recently viewed | per user | streamed late or client-side, lazy below fold |

- **Variant in URL:** `?color=blue&size=42` → shareable, back-button safe, drives SSR of correct image/price; `rel=canonical` to base product to avoid duplicate-content.
- **SEO:** real SSR HTML; Product JSON-LD (name, image, offers.price, availability, aggregateRating); canonical, hreflang, clean URLs; CWV is a ranking signal.
- **LCP:** hero `<img>` with correct `sizes`, AVIF/WebP, `fetchpriority="high"`, never lazy; preload only if it's a CSS background. Other gallery images lazy.
- **CLS:** reserve space for price/stock/recs skeletons; font fallback metric overrides (`size-adjust`) and subsetting.
- **INP:** keep the variant picker and add-to-cart island small; defer third parties (reviews widget, chat, analytics).
- **A/B tests:** decide variant at the edge (cookie bucket → cache key) instead of client-side flicker scripts that block render.
- **Resilience:** each region has its own error boundary. Inventory down → "check availability in cart"; recs down → render nothing; buying must never break. Cart writes idempotent with retry.
- **Caching:** HTML shell + product content keyed by product + locale (+ experiment bucket); purge by product tag on catalog change; price short TTL or uncached; personalized fragments `Cache-Control: private`, never in shared caches.

## Mental model / flow
```
                ┌──────────────────────── CDN / Edge ────────────────────────┐
Browser ─GET──► │ cache key: product+locale+abBucket                          │
                │  HIT: static shell + product content (ISR, tag=product:123) │
                │  edge fn: assign A/B bucket, geo → currency                 │
                └───────────────┬─────────────────────────────────────────────┘
                                │ streamed HTML (chunks in priority order)
       ┌────────────────────────┼───────────────────────────────┐
       ▼                        ▼                               ▼
  [1] shell+hero img     [2] price/stock (Pricing svc,   [3] reviews (Reviews svc)
      LCP element            no cache / short TTL)       [4] recs (per user, private,
                                                              lazy / client)
Browser hydrates islands only: VariantPicker · AddToCart · Gallery
AddToCart ─POST (Idempotency-Key)─► Cart API      Catalog change ─► purge tag product:123
```

## Code sketch
```tsx
// RSC/streaming-style composition (framework-agnostic shape)
export default async function ProductPage({ id, variant }: Props) {
  const product = await getProduct(id);            // cached, tag: product:id
  return (
    <>
      <ProductJsonLd product={product} />
      <Gallery hero={product.images[0]} priority />  {/* fetchpriority=high */}
      <h1>{product.title}</h1>
      <ErrorBoundary fallback={<p>Check availability in cart</p>}>
        <Suspense fallback={<PriceSkeleton />}><PriceAndStock id={id} variant={variant} /></Suspense>
      </ErrorBoundary>
      <AddToCartIsland id={id} variant={variant} />
      <Suspense fallback={<ReviewsSkeleton />}><Reviews id={id} /></Suspense>
      <ErrorBoundary fallback={null}><LazyRecs id={id} /></ErrorBoundary>
    </>
  );
}
```

## Trade-offs & pitfalls
- Streaming price inline keeps SEO price accurate but adds request-time dependency; client-fetched price is cacheable HTML but crawlers may see stale/none. JSON-LD price should match what users see.
- Over-segmenting cache keys (per user) kills hit rate; keep personalization out of the shared HTML.
- Hydrating the whole page instead of islands pushes INP and TBT up.
- Edge A/B buckets multiply cache variants; limit concurrent experiments on the PDP.
- Flash sales: stock goes stale fast; show "limited stock" softly and enforce truth at checkout.

## Likely follow-ups
- *SSG vs ISR vs SSR?* SSG for long-tail-stable content, ISR/tag revalidation for catalog updates, SSR/stream for fresh slices.
- *How measure success?* RUM p75 LCP/INP/CLS by device class, add-to-cart rate, conversion per experiment.
- *Image pipeline?* Upload once, CDN transforms by width/format, `srcset` + `sizes`, blur placeholder.
- *Localization of price?* Currency from geo/edge + user setting; part of cache key or fetched separately.

## Say it in 60 seconds
I'd split the page by how fresh each part must be. Product content and images are the same for everyone, so they're statically generated or edge-cached with tag-based purge when the catalog changes. Price and stock are fetched at request time and streamed, or client-fetched into a sized skeleton. Reviews stream behind Suspense. Recommendations are per user and load late, never in a shared cache. Only the variant picker, gallery and add-to-cart hydrate as islands. Variant lives in the URL with a canonical to the base product, and I emit Product JSON-LD. For LCP the hero image is high priority, never lazy, in AVIF or WebP. A/B buckets are decided at the edge, and each region has its own error boundary so a failing recs or inventory service never blocks buying.
