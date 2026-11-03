# Micro-frontends and Module Federation: when do they pay off, and how do they fail?
**Round:** 13 · Architecture at Scale · **Level:** Principal · **Time:** 20 min · **Tags:** micro-frontends · module federation · architecture
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: three teams want to carve a ~400-page admin app into Module Federation remotes. Is it worth it, and how do you avoid a mess?

## What they're really testing
Whether you treat micro-frontends as an org/deployment decision (Conway's law) rather than a tech fashion, and whether you know the runtime failure modes before you sign up for them.

## Core answer (key points)
- **What they buy:** team autonomy and independent deploys, split by business domain. Also a vehicle for incremental stack migration.
- **What they cost:** shared-dependency version skew, risk of duplicate React copies, more JS and loading waterfalls, cross-app routing/state complexity, visual drift between teams.
- **Module Federation solves one thing:** loading and sharing code at runtime. It does not give you contracts, ownership, or UX consistency. Those are platform-team work.
- **Default recommendation:** a modular monorepo with enforced boundaries and separate deploy units first. Reach for runtime composition only for the one or two areas where independent deploy is genuinely worth the tax.
- **Pick the composition style per need:**
  | Style | Independence | Main cost | Fit |
  |---|---|---|---|
  | Monorepo, build-time packages | Shared release | Low | Most orgs |
  | Server/edge fragments (ESI) | High | Infra | Content sites |
  | Route-level split (app per path) | High | Full reloads or shell router | Distinct product areas |
  | Runtime (MF, import maps) | High | Version/shared deps | Many teams, one SPA shell, migrations |
  | iframes | Total | a11y, perf, UX seams | Untrusted / legacy embeds |
- **Integration contracts:** shell owns top-level routes and auth; remotes own sub-routes under a basename. Communicate through mount props, URL, and a small typed event bus. Never share stores directly. Design system as a singleton with strict semver. A perf budget per remote.

## Mental model / flow
```
Browser -> shell (owns router, auth client, DS theme, query client)
             |-- loads manifest (which remote version is live)
             |-- lazy import remote 'billing/App'
                    |-- shared singletons resolved from shell (react, react-dom, DS)
                    |-- on 404/timeout -> ErrorBoundary fallback + retry
```

## Code sketch
```ts
// shell config (rspack/webpack MF). Singletons for anything with global state.
new ModuleFederationPlugin({
  name: 'shell',
  remotes: { billing: 'billing@https://cdn.example.com/billing/remoteEntry.js' },
  shared: {
    react: { singleton: true, requiredVersion: '^19.0.0' },
    'react-dom': { singleton: true, requiredVersion: '^19.0.0' },
    '@org/ui': { singleton: true, requiredVersion: '^4.0.0' },
  },
});

// shell usage: never let a remote white-screen the app
const Billing = lazy(() => import('billing/App'));
<RemoteBoundary name="billing" fallback={<BillingUnavailable />}>
  <Suspense fallback={<PageSkeleton />}><Billing basename="/billing" /></Suspense>
</RemoteBoundary>;
```

## Trade-offs & pitfalls
- Two Reacts (missing `singleton`) = broken hooks and context. Same for router, theme provider, query client.
- Version skew: remote built on a newer minor may or may not work in the shell. Policy: shell owns platform versions, remotes declare ranges, CI checks compatibility.
- Splitting by technical layer (header team, footer team) rather than domain forces cross-team changes on every feature.
- Too granular ("one MFE per widget") multiplies overhead.
- No platform team means every team reinvents build, auth, telemetry.
- Independent deploys without contract tests = production breakage. Shared mutable global state recreates monolith coupling, but worse.

## Likely follow-ups
- **How do you test it?** Contract tests at the mount boundary, E2E against the composed shell in staging, and a compatibility matrix in CI.
- **How do you observe it?** Tag every error/RUM event with remote name + version; per-remote bundle and vitals budgets.
- **Exit criteria if it fails?** Remotes are still packages; fold them back into build-time composition in the monorepo.
- **Import maps vs MF?** Import maps are a browser-native URL mapping for ESM; MF adds shared-dep negotiation. Choose MF when you need singletons negotiated at runtime.
- **What would make you say no?** Few teams, rarely blocked on each other's releases, heavy UI sharing.

## Say it in 60 seconds
Micro-frontends are an organizational tool: they let domain teams ship independently, and they help migrate between stacks. The price is runtime complexity, version skew, extra JS and design drift. Module Federation only handles runtime code sharing; contracts, ownership and consistency are still your job. So I'd start by asking how many teams there are and how often releases block them. Usually the answer is a modular monorepo with enforced boundaries and independent deploy units, plus runtime federation for only the one or two areas that truly need it. If we do federate, the shell owns routing, auth and the design system as singletons, remotes get error boundaries and a version manifest, every event is tagged with remote version, and contract tests gate deploys.
