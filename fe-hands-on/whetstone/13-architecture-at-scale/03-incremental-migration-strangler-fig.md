# Lead an incremental migration (for example AngularJS to React) without a rewrite freeze
**Round:** 13 · Architecture at Scale · **Level:** Principal · **Time:** 20 min · **Tags:** migration · strangler fig · angularjs
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: 300 AngularJS screens, roadmap cannot pause. Run the migration to React.

## What they're really testing
Strangler-fig mechanics plus the leadership half: sequencing, guardrails, measuring progress, and actually finishing the last 10%.

## Core answer (key points)
- **No big-bang rewrite.** Old and new run side by side; features keep shipping.
- **Pick a bridge** (often several over time):
  | Bridge | How | When |
  |---|---|---|
  | New-inside-old | Mount React roots inside legacy pages via a directive wrapper | Day 1: new widgets in React |
  | Old-inside-new | React shell hosts legacy routes | Mid-migration |
  | Route split | Router sends migrated paths to React, rest to legacy | Whole-screen ownership |
  | Micro-frontends | Federated shell loads both | Many teams, long timeline |
- **Foundations first:** React build pipeline, shared design tokens, shared API client, auth/session bridge, routing bridge, observability.
- **Guardrail:** no new features in legacy (lint rule or review policy). Otherwise the target moves.
- **Prioritize by value:** high-traffic + high-churn screens first (biggest payoff); a few easy screens early to set patterns and morale.
- **Per-screen definition of done:** feature parity, permissions, analytics events, a11y, perf budget, E2E tests ported, legacy code deleted.
- **Measure publicly:** screens/LOC remaining on a dashboard; bundle size, defect rate, dev velocity.
- **Plan the finish:** removing the bridge and the legacy runtime is where migrations stall. Budget it explicitly.

## Mental model / flow
```
Phase 0  foundations + guardrail
Phase 1  React islands inside AngularJS pages
Phase 2  route-level: migrated routes -> React app
Phase 3  legacy hosted inside React shell (minority)
Phase 4  delete bridge + AngularJS runtime  <- the stall point
```

## Code sketch
```tsx
// Own sketch: AngularJS directive that hosts a React root and tears it down
angular.module('app').directive('reactInvoiceList', () => ({
  restrict: 'E',
  scope: { customerId: '<' },
  link(scope: any, el: JQLite) {
    const root = createRoot(el[0]);
    const render = () => root.render(<InvoiceList customerId={scope.customerId} />);
    const stop = scope.$watch('customerId', render);
    scope.$on('$destroy', () => { stop(); root.unmount(); });
  },
}));
```

## Trade-offs & pitfalls
- **Two UX patterns at once:** share tokens, scope/prefix CSS to stop leaks both ways.
- **Double bundle:** lazy-load the AngularJS runtime only on legacy routes.
- **Cross-framework state:** keep it server-side or in a framework-agnostic store with subscriptions; don't bridge two state systems by hand.
- **Digest cycle vs React rendering:** changes from React back into AngularJS need `$apply`/`$evalAsync`, or the legacy view won't update.
- **Stalling and morale:** tie migration to product work ("billing redesign happens in React"). Celebrate deletions.

## Likely follow-ups
- **How do you convince product?** Frame in their metrics: faster feature delivery on migrated areas, fewer defects, hiring. Bundle migration with planned redesigns.
- **How do you prevent regressions?** Per-screen parity checklist, analytics event diffing, E2E ported before cutover, flag-gated rollout of the new route.
- **How do you know you're done?** AngularJS removed from package.json and the bundle; bridge code deleted.
- **What if a screen is rarely used?** Migrate last or delete it; usage data can retire screens for free.

## Say it in 60 seconds
I never freeze features for a rewrite. I'd run a strangler fig: build foundations once (React pipeline, shared tokens, API client, auth and routing bridges, telemetry), then add a guardrail that no new features go into AngularJS. New widgets mount as React roots inside legacy pages from day one; then we migrate route by route, prioritizing high-traffic, high-churn screens, with a parity checklist per screen covering permissions, analytics, a11y, perf and E2E tests, and we delete legacy code as each ships. Progress is visible on a dashboard, and the last phase, removing the bridge and runtime, is planned explicitly because that's where migrations stall.
