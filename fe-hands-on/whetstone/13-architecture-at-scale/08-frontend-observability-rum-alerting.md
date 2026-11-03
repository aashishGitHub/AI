# Frontend observability: errors, RUM, tracing, source maps and alerting people trust
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** observability · rum · error tracking
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: after a release, conversion drops ~4%, no alert fired, the error tracker is noisy. Design observability that catches issues before users complain.

## What they're really testing
Symptom-based alerting tied to releases, not "install Sentry". Signal quality, ownership, privacy and cost.

## Core answer (key points)
- **Four signals:**
  1. **Errors:** grouped, deobfuscated with privately uploaded source maps, tagged with release, route, user/tenant context, breadcrumbs.
  2. **Performance (RUM):** Web Vitals (LCP, INP, CLS) and custom product timings from real users, per route.
  3. **Traces:** frontend spans propagate W3C `traceparent` to the backend so a slow click maps to a slow service.
  4. **Business/product events:** did checkout complete? This is what would have caught the 4% drop.
- **Alert on user-impacting symptoms,** not every exception: error rate per release vs baseline, p75 vitals per route, failed critical journeys, conversion funnel step rates.
- **Tie everything to releases and flags** so a regression points at a change; auto-pause rollouts when release health degrades.
- **Synthetics** for critical journeys from several regions catch total breakage even with low traffic.
- **Frontend SLOs:** e.g. share of page loads without a JS error; p75 INP target on key routes.
- **Ownership:** route/component ownership metadata routes alerts to the right team.

## Mental model / flow
```
release v4.12 deploy (canary 5%)
  -> RUM + errors + funnel events tagged version=v4.12, flags=[...]
  -> compare vs v4.11 baseline for 30 min
  -> breach? auto-pause rollout + page owning team with trace/replay links
```

## Code sketch
```ts
// Own sketch: one init point, consistent context, PII scrubbing
initRum({
  service: 'web-app',
  version: RELEASE_ID,            // must match uploaded source map release
  sessionSampleRate: 20,
  traceUrls: [/^https:\/\/api\.example\.com/],   // inject traceparent here only
  beforeSend: e => redact(e),     // emails, tokens, query strings
});
setContext({ tenantTier, activeFlags: flags.keys() });

performance.mark('checkout:submit');
await submitOrder();
performance.measure('checkout:confirmed', 'checkout:submit');
track('checkout_completed', { release: RELEASE_ID });
```

## Trade-offs & pitfalls
- Public source maps leak code; upload privately at build time.
- Noise kills trust: filter browser-extension errors, benign `ResizeObserver` loop messages, aborted fetches; fingerprint and rate-limit.
- Sampling saves cost but can hide rare-segment regressions; sample sessions, keep errors at higher rate.
- PII in URLs, breadcrumbs and session replay. Mask by default, scrub in `beforeSend`.
- Only propagate trace headers to your own origins (CORS preflight and leaking trace ids to third parties).
- Averages hide pain; use percentiles and segment by device/network.

## Likely follow-ups
- **Why didn't the error tracker catch the 4% drop?** The bug may not throw (wrong button state, slow INP, broken analytics). Only funnel/business metrics per release catch it.
- **How do you use this in an incident?** Filter by release and flag, compare cohorts, jump from RUM session to trace to backend logs, roll back or kill-switch.
- **Session replay worth it?** For hard bugs yes, with strict masking and sampling; legal review required.
- **Which vendor?** Datadog RUM, Sentry, others; principles are vendor-neutral. Verify current feature sets in docs.

## Say it in 60 seconds
I'd collect four signals: errors with private source maps and release tags, real-user performance per route, traces that propagate traceparent to the backend, and business events like checkout completion. The 4% drop shows why the last one matters: plenty of regressions never throw. Alerts should fire on user-impacting symptoms compared against the previous release: error rate, p75 vitals, funnel step rates, plus synthetic checks for critical journeys, and a breach should auto-pause the rollout and page the owning team. Everything is tagged with release and active flags so a regression points at a change, PII is scrubbed before send, and noise is filtered so people trust the alerts.
