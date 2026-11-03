# Run a design system as a product: versioning, contribution, adoption and breaking changes
**Round:** 13 · Architecture at Scale · **Level:** Principal · **Time:** 15 min · **Tags:** design systems · governance · versioning
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: 20 product teams, low adoption, teams fork components, last quarter's breaking change caused outages.

## What they're really testing
Product thinking applied to a platform: customers (product teams), value proposition, change management, metrics, and governance.

## Core answer (key points)
- **Win by being the fastest path,** not by mandate. Teams adopt what makes them ship faster with better UI.
- **Scope in layers:** tokens (color, space, type, radius, motion) in a platform-neutral format (DTCG JSON) compiled to CSS vars/TS/mobile; accessible primitives (Button, Dialog, Menu, Combobox); documented patterns (forms, tables, empty states, layouts).
- **Docs as product:** live examples, props tables generated from types, a11y notes, do/don't.
- **Change management (fixes the outage):** semver + changesets; small frequent releases; deprecate before remove (dev warnings, lint rule, codemods via jscodeshift/ts-morph); visual regression tests per component; published support window (e.g. N-1 majors).
- **Contribution model:** hybrid usually wins: core owns primitives and quality bar; product teams contribute patterns through an RFC with review.
- **Metrics:** % UI from system components (static import analysis), count of forks/detached components and override CSS, time to build a standard screen, a11y defects in system components.
- **Fix forking:** interview forkers, add escape hatches (composition, slots, `asChild`-style APIs), close gaps fast.

## Mental model / flow
```
Breaking change lifecycle
  RFC -> add new API alongside old -> deprecation warning + lint rule
      -> codemod published -> track call sites to zero -> remove in next major
```

## Code sketch
```ts
// Own sketch: dev-only deprecation warning that codemods/lint can target
export function Button({ kind, variant, ...rest }: ButtonProps) {
  if (process.env.NODE_ENV !== 'production' && kind) {
    warnOnce('Button: `kind` is deprecated, use `variant`. Run `npx @org/ui-codemods button-variant`.');
  }
  return <ButtonImpl variant={variant ?? mapKind(kind)} {...rest} />;
}
```

## Trade-offs & pitfalls
| Model | Pros | Cons |
|---|---|---|
| Centralized | Consistency | Bottleneck |
| Federated | Scale | Inconsistency without strong review |
| Hybrid (core primitives, RFC patterns) | Balance | Needs process |
- Too generic -> teams can't build what they need -> forks. Too rigid -> no escape hatches -> forks.
- Breaking changes without migration tooling strand teams on old majors.
- Launch-then-abandon: no ownership after v1.
- Figma library and code library drifting apart; tokens should be the shared source.

## Likely follow-ups
- **How do you prove value?** Before/after time-to-ship on a standard screen; a11y defect counts; consistency audits.
- **Who funds it?** Treat it as a platform team with a roadmap driven by consumer demand.
- **How do you handle a team needing something custom now?** Escape hatch now, contribution path to upstream it, track as debt.
- **Monorepo vs published package?** Published with semver if consumers are many repos; in-monorepo still benefits from changesets and visual tests.

## Say it in 60 seconds
I'd run the design system like a product whose customers are the 20 teams. Layered scope: tokens, accessible primitives, documented patterns, with docs that show live examples and generated prop tables. The outage tells me change management is broken, so: semver with changesets, small releases, deprecate before removing with dev warnings, lint rules and codemods, visual regression tests, and a published support window. A hybrid contribution model where the core team owns primitives and teams contribute patterns via RFC. Then I'd measure adoption by import analysis and fork count, talk to the teams that forked, and close their gaps, because adoption comes from being the fastest path, not from mandates.
