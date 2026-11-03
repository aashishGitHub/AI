# ESM vs CommonJS: live bindings, cycles, tree shaking and interop
**Round:** 01 · JavaScript Internals · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** modules · esm · commonjs
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Whether you can lead a CJS→ESM migration: explain the semantic gap (static vs dynamic, live vs copied), predict cycle behaviour, know why tree shaking regresses, and set packaging rules for a design system.

## Core answer (key points)
- **ESM** is static: the import/export graph is known before any code runs. Loading is fetch → link → evaluate. Exports are **live, read-only bindings**. Supports top-level await. Top-level `this` is `undefined`.
- **CJS** is dynamic: `require` runs the module synchronously and returns whatever `module.exports` is *at that moment*. Destructuring copies values. Top-level `this` is `module.exports`.
- Static structure is what makes **tree shaking**, TLA and predictable cycles possible.
- Interop pain comes from mapping one model onto the other (default vs named, `__esModule`, dual packages).

| | ESM | CJS |
|---|---|---|
| Resolution | before run | at run, can be conditional |
| Exports | live bindings | value snapshot |
| Loading | async graph | sync, in order |
| TLA | yes | no |
| Tree shaking | reliable | heuristic |

## Mental model / flow
Cycles, A imports B, B imports A:
- **ESM**: whole graph linked first. B can reference A's binding, but if A hasn't evaluated yet: `let`/`const`/`class` → TDZ ReferenceError; hoisted `function` declarations work.
- **CJS**: B gets A's **partially filled** `module.exports` → fields are `undefined`.
- Rule for app code: cycles are a design smell. Lint them (`import/no-cycle`, madge, dependency-cruiser) and break them by extracting shared types/constants into a leaf module.

## Code sketch
```js
// store.mjs
export let version = 1;
export const bump = () => { version++; };

// app.mjs
import { version, bump } from './store.mjs';
bump();
version;        // 2, live view
// version = 9; // TypeError: imports are read-only

// CJS equivalent: const { version } = require('./store') would stay 1 forever
```
Design-system `package.json` shape (illustrative):
```json
{
  "type": "module",
  "sideEffects": ["**/*.css"],
  "exports": {
    ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js" },
    "./button": { "types": "./dist/button.d.ts", "import": "./dist/button.js" }
  }
}
```

## Trade-offs & pitfalls
Tree shaking fails when:
- the package ships CJS (`lodash` vs `lodash-es`);
- modules have import-time side effects and the package doesn't declare `sideEffects`;
- you import a namespace and index it dynamically (`utils[name]()`);
- barrel files re-export everything and something in the chain has side effects.

Interop:
- `import x from 'cjs-pkg'` gives you `module.exports`; named imports only work if Node/bundler can statically detect them.
- `__esModule` flag: transpiled ESM-as-CJS marks itself so default import maps to `exports.default`; toolchains disagree → `x.default.default`.
- **Dual package hazard**: shipping both CJS and ESM can load two copies → two React contexts, two stores, broken singletons.
- Newer Node versions (the site says ≥ 22) can `require()` a synchronous ESM graph; reduces friction, not the semantic gap. Verify exact version/flag status in current Node docs.

Migration order I'd propose: leaf utilities first, add `exports` maps, kill cycles before flipping `"type": "module"`, add a bundle-size check per entry before and after.

## Likely follow-ups
- **Are barrel files bad?** Not inherently, but they make bundlers, test runners and dev servers parse/evaluate many modules to find one export and defeat shaking when anything has side effects.
- **What does `import()` change?** It's an async split point: separate chunk, fetched on demand. Pair with preload on intent (hover/viewport).
- **How do you stop "one Button pulls the whole library"?** ESM-only, per-component `exports` entries, `sideEffects` declared, explicit CSS imports, and `size-limit` per entry in CI so regressions fail the build.
- **Why can't CJS do TLA?** `require` is synchronous and must return a value now.

## Say it in 60 seconds
ES modules are static: the graph is resolved and linked before anything runs, and exports are live read-only bindings. CommonJS is dynamic: `require` executes synchronously and hands back a snapshot of `module.exports`. That difference explains the migration symptoms. In a cycle ESM gives you a TDZ error for an uninitialised `let` while CJS gives you `undefined` from a half-built exports object, so lint cycles and extract leaf modules. Tree shaking needs static ESM and honest `sideEffects` metadata; CJS deps, side-effectful imports and barrels defeat it. Interop issues, the `__esModule` default wrapping and the dual-package hazard that loads two copies of a singleton, come from mapping one model onto the other. For a design system I'd ship ESM only with per-component `exports` and a size check per entry point in CI.
