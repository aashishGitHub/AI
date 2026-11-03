# Monorepos for frontend: pnpm workspaces, Nx or Turborepo, boundaries and CI caching
**Round:** 13 · Architecture at Scale · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** monorepo · pnpm · nx
Source: https://whetstone-v1.vercel.app/#architecture-at-scale

Scenario: 12 frontend repos, duplicated tooling, painful cross-repo changes. Propose a monorepo and the migration.

## What they're really testing
That you know a monorepo is only good with three supports (workspaces, cached/affected task runner, enforced boundaries) and that you can migrate without stopping teams.

## Core answer (key points)
- **Why:** atomic cross-package changes, one version of each dependency, cheap reuse, one place for tooling.
- **Three tool layers:**
  1. Package manager with workspaces (pnpm: strict, fast, content-addressed store).
  2. Task runner with a dependency graph, caching and "affected" detection (Nx or Turborepo), plus **remote cache** shared between CI and laptops.
  3. **Boundary enforcement** so it does not become a big ball of mud: tag packages and lint imports.
- **Layout:** `apps/*` (deployables) and `packages/*` (design system, typed data client, domain feature packages, shared eslint/tsconfig configs).
- **Boundary rules (example):** features cannot import other features; UI cannot import data clients; only apps compose features. Use `exports` in package.json to block deep imports.
- **Scale aids:** TS project references for incremental type checks; CODEOWNERS for review routing.
- **Migration:** import repos one at a time preserving history (`git subtree`/similar), wire them into the task graph, unify configs gradually, then dedupe shared code. Never a freeze.

## Mental model / flow
```
PR changes packages/ui
  -> task graph: ui -> feature-billing -> apps/console
  -> run build/test/lint only for those three ("affected")
  -> hashes match remote cache? replay outputs, skip work
```

## Code sketch
```jsonc
// turbo.json: "^build" = build my dependencies first
{
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": ["dist/**"] },
    "test":  { "dependsOn": ["^build"], "outputs": ["coverage/**"] },
    "lint":  {}
  }
}
```
```js
// Nx-style boundary rule idea (eslint)
depConstraints: [
  { sourceTag: 'type:feature', onlyDependOnLibsWithTags: ['type:ui', 'type:util', 'type:data'] },
  { sourceTag: 'type:ui',      onlyDependOnLibsWithTags: ['type:ui', 'type:util'] },
]
```
CLI to remember: `turbo run test --filter=...[origin/main]` or `nx affected -t test`.

## Trade-offs & pitfalls
- Upfront investment in tooling and CI; at very large scale, repo size and IDE performance hurt.
- Visibility of everything is great for refactors, but needs CODEOWNERS or reviews drown.
- Atomic changes make tight coupling easy; boundaries must be enforced by lint/CI, not by convention.
- Cache correctness: undeclared inputs (env vars, generated files) cause stale cache hits. Declare them.
- Versioning: decide between "everything at HEAD" (internal packages unversioned) and published packages via changesets. Mixing without a rule creates confusion.

## Likely follow-ups
- **Nx vs Turborepo?** Turborepo is lighter (task pipeline + cache); Nx adds generators, project graph tooling and built-in boundary lint. I'm not certain of every current feature gap; verify against current docs.
- **How do you keep CI fast?** Affected-only + remote cache + parallelism; target "PR CI time" as a tracked metric.
- **Publishing to external consumers?** Changesets for semver and changelogs per package.
- **When is a monorepo wrong?** Truly independent products with different release, security or language needs.

## Say it in 60 seconds
A monorepo makes cross-package changes atomic and keeps versions aligned, but it only works with three things: pnpm workspaces for packages, a task runner like Nx or Turborepo that builds only what's affected and shares a remote cache, and enforced import boundaries so features don't reach into each other. I'd lay it out as apps plus packages for the design system, data client, feature domains and shared configs, add CODEOWNERS and TS project references, and migrate repo by repo with history so no team stops shipping. The honest downsides are upfront tooling cost, CI and cache correctness, and the temptation to couple things just because you can.
