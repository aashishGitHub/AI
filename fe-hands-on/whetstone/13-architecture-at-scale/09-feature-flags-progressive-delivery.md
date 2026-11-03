# Feature flags and progressive delivery: kill switches, flag debt and testing
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** feature flags · progressive delivery · canary
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: big features ship behind flags, nobody removes them, and a half-enabled flag combination caused an incident.

## What they're really testing
That you know flags separate deploy from release, and that you manage their real cost: combinatorial code paths, flicker, and debt.

## Core answer (key points)
- **Deploy is not release:** code ships dark, then turns on for internal users, a percentage, a segment, everyone. Rollback is a toggle, not a redeploy.
- **Flag types with different lifetimes:** release (short-lived), experiment (until decided), ops/kill switch (long-lived), permission/entitlement (permanent, arguably not a "flag").
- **Evaluation rules:**
  - No flicker: evaluate before first render (server-side, or bootstrap values into HTML), not via a post-mount fetch that swaps UI.
  - Typed registry (`flags.newBilling: boolean`) instead of string lookups.
  - Sticky bucketing by user/account id so users don't flip variants.
  - Kill switches fail to the safe default when the flag service is unreachable.
  - Attach active flags to RUM/error events to correlate regressions.
- **Hygiene (fixes flag debt):** owner, type and removal date on every flag; CI reports flags past expiry or at 100%; remove the dead branch and the flag in one PR.
- **Combination incident fix:** declare dependencies between flags, limit concurrently-in-flight release flags per area, test critical flags in both states, and avoid nesting flags.
- **Progressive delivery:** canary (small traffic slice gets the new build), automated analysis on error rate and vitals, automatic rollback. For frontends: versioned immutable assets plus routing a percentage of users to the new `index.html`.

## Mental model / flow
```
create flag (owner, type, expiry) -> ship dark -> internal -> 1% -> 10% -> 50% -> 100%
      each step: watch release health; breach -> auto rollback
100% for N days -> cleanup PR removes flag + old branch -> CI verifies key unused
```

## Code sketch
```tsx
// Own sketch: typed flags, bootstrapped so first render is already correct
type Flags = { newBilling: boolean; checkoutKillSwitch: boolean };
const FlagsContext = createContext<Flags>(SAFE_DEFAULTS);

export const useFlag = <K extends keyof Flags>(k: K) => useContext(FlagsContext)[k];

// root: values come from server-rendered bootstrap, not a post-mount fetch
<FlagsContext.Provider value={window.__BOOTSTRAP__?.flags ?? SAFE_DEFAULTS}>
  <App />
</FlagsContext.Provider>;

function BillingPage() {
  return useFlag('newBilling') ? <BillingV2 /> : <BillingV1 />;
}
```

## Trade-offs & pitfalls
- Each flag doubles possible paths; N live flags in one area means 2^N combinations nobody tests.
- Client-only evaluation causes flicker and layout shift; also exposes unreleased feature names in the bundle.
- Long-lived release flags rot: old branches stop compiling against new code, or get "fixed" without anyone testing them.
- Flags are not authorization. Entitlements must be enforced server-side.
- Vendor lock-in: an abstraction like OpenFeature keeps the provider swappable (verify current SDK support for your stack).

## Likely follow-ups
- **How do you test flagged code?** Unit tests for both branches of critical flags; E2E with flags forced via override; a "all-new" and "all-old" config in CI.
- **Trunk-based development link?** Flags let unfinished work merge to main daily without exposing it.
- **Experiment vs release flag?** Experiments need assignment logging and stats; release flags only need safe rollout.
- **How do you roll back a frontend canary?** Point the routing back to the previous immutable `index.html`; old hashed assets are still on the CDN.

## Say it in 60 seconds
Flags decouple deploy from release: code ships dark and turns on progressively, and rollback is a toggle. But each flag multiplies code paths, so I manage their lifecycle: every flag has an owner, type and expiry, CI flags anything stale or fully rolled out, and cleanup removes both the flag and the dead branch in one PR. On the client I evaluate flags before first render from bootstrapped values to avoid flicker, type them in a registry, bucket stickily by user, make kill switches default to safe, and attach active flags to telemetry. For the combination incident, I'd declare flag dependencies, test critical flags in both states, and pair rollouts with canary analysis that auto-rolls back on error or vitals regressions.
