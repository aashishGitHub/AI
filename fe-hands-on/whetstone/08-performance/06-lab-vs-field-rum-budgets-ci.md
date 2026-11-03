# Lab vs field data, RUM, and enforcing performance budgets in CI
**Round:** 08 · Performance · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** rum · lighthouse ci · performance budgets
Source: https://whetstone-v1.vercel.app/#performance

Scenario: leadership wants "no performance regressions" after a redesign. Lighthouse in CI is flaky, and field numbers differ from lab. Design measurement and enforcement.

## What they're really testing
Understanding why lab and field differ, designing gates that are strict where signals are deterministic and lenient where they're noisy, and the org model (ownership, triage, budget changes).

## Core answer (key points)
- **Field (RUM, CrUX):** what real users experience, distribution across devices/networks/states. Truth, but lagging and noisy per release.
- **Lab (Lighthouse, WebPageTest, Playwright traces):** controlled, reproducible, debuggable; one device profile, cold cache, no real interactions (no INP).
- **Why they disagree:** device/network mix, warm vs cold cache, logged-in heavier content, geography/CDN, third-party scripts and A/B tools behaving differently, lab throttling being simulated.
- **Per-PR lab gates:**
  - **Hard gate** on deterministic signals: bundle bytes per entry (size-limit), request counts, image weight.
  - **Soft gate** on timing metrics: Lighthouse CI with 3-5 runs, median, assertions with tolerance; warn and require a look rather than block on small deltas. Use dedicated/stable runners.
- **RUM pipeline:**
  - Collect Core Web Vitals with attribution plus custom product marks ("search results visible", "editor ready").
  - Tag every event: route, release, device memory/cores, effective connection, logged-in vs anonymous.
  - Sample if traffic is large but keep enough per route for stable p75.
  - Annotate releases so a regression maps to a deploy; alert on **sustained** p75 regressions per route, not spikes.
- **Org:** route-owning team owns the budget and the page; PR comments show cost and the dependency that caused it; budget changes need an explicit, reviewed exception; connect perf to business metrics (conversion by LCP bucket) to fund the work.

## Mental model / flow
```
PR ─► build ─► size-limit (HARD) ─► LHCI x5 median (SOFT, warn) ─► merge
                                                                    │
                                                          deploy (release tag)
                                                                    │
users ─► web-vitals + custom marks ─► /rum ─► warehouse ─► p75 by route × device × release
                                                                    │
                                              sustained regression? ─► alert route owner ─► triage
```

## Code sketch
```json
// lighthouserc.json (sketch)
{
  "ci": {
    "collect": { "numberOfRuns": 5, "url": ["http://localhost:4173/", "http://localhost:4173/product/1"] },
    "assert": {
      "assertions": {
        "largest-contentful-paint": ["warn", { "maxNumericValue": 2500, "aggregationMethod": "median" }],
        "total-blocking-time": ["warn", { "maxNumericValue": 300 }],
        "cumulative-layout-shift": ["error", { "maxNumericValue": 0.1 }],
        "resource-summary:script:size": ["error", { "maxNumericValue": 350000 }]
      }
    }
  }
}
```
```ts
// custom product moment alongside web-vitals
performance.mark('search:results-visible');
const [entry] = performance.getEntriesByName('search:results-visible');
navigator.sendBeacon('/rum', JSON.stringify({ name: 'search_ready', value: entry.startTime, route: location.pathname, release: RELEASE }));
```

## Trade-offs & pitfalls
- Blocking merges on noisy Lighthouse timings trains engineers to rerun until green and ignore the gate.
- CLS in lab is usually deterministic enough to hard-gate; LCP/TBT less so on shared runners.
- RUM alert thresholds too tight = alert fatigue; too loose = regressions ship. Use relative change over a baseline window and a minimum sample size.
- Mixing releases in one window hides attribution; canary/percentage rollouts let you compare cohorts.
- Privacy: RUM payloads must not include PII (URLs with query params, user ids); scrub at the edge.
- CrUX only covers Chrome users above traffic thresholds and is a 28-day window; own RUM is needed for release-level signal.

## Likely follow-ups
- **What would you hard-gate on day one?** Bundle size per entry and CLS; everything else warn until baselines are stable.
- **How do you make Lighthouse less flaky?** Median of multiple runs, dedicated runners, fixed throttling, a production build with stable fixtures and mocked third parties.
- **Who gets paged?** No paging for perf usually; route owners get an alert/ticket with the release diff and attribution.
- **How do budgets evolve?** Ratchet: when a team beats its budget, lower it; exceeding needs an exception with a payback plan.
- **How do you prove business value?** Bucket sessions by LCP/INP and compare conversion/bounce; run A/B tests that add artificial delay only if ethically acceptable.

## Say it in 60 seconds
I use lab data to debug and gate pull requests, and field data to know what users actually feel; they disagree because real users have slower devices, cold caches, heavier logged-in pages and different third-party behaviour. Per PR I hard-gate on deterministic things like bundle size per entry, and run Lighthouse CI several times taking the median as a soft gate, so flakiness doesn't block merges. In production I collect web vitals with attribution and a few custom product moments, tag every event with route, release and device class, and alert the owning team on sustained p75 regressions per route after a release. Each route team owns its budget, PRs show the cost and the dependency that caused it, and exceeding a budget needs an explicit exception.
