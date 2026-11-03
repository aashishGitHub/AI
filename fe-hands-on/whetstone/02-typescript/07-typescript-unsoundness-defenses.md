# Where is TypeScript unsound, and how do you defend against it?
**Round:** 02 · TypeScript for Real Codebases · **Level:** Principal · **Time:** 12 min · **Tags:** soundness · variance · any
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
"TS says it's fine, yet it throws." Show concrete holes, the flags and lint rules that close them, and, at principal level, how you roll strictness out across a huge codebase.

## Core answer (key points)
- TS **deliberately trades soundness for usability**; a fully sound checker would reject a lot of idiomatic JS.
- Known holes:
  1. `any` leakage (`JSON.parse`, `res.json()`, untyped libs) spreads silently.
  2. **Unchecked index access**: `record[key]` and `arr[i]` assumed present.
  3. **Array covariance**: `Dog[]` assignable to `Animal[]`, then push a `Cat`.
  4. **Method parameter bivariance**: method-syntax members accept narrower param types even under `strictFunctionTypes`.
  5. Type assertions (`as`) and non-null `!`.
  6. Optional vs explicitly `undefined` (`{ timeout: undefined }` passes `timeout?: number`).
  7. Narrowing not invalidated by calls: after `if (o.x)`, a function that mutates `o` doesn't reset the narrowing.
- Defences: strict flags, lint rules banning unsafe `any`, boundary validation, review norms on assertions.

## Mental model / flow
```
holes enter at:  boundaries (any/JSON) | escape hatches (as, !) | variance rules | index access
close with:      validation            | lint + review          | property-syntax fns | noUncheckedIndexedAccess
```

## Code sketch
```ts
const prices: Record<string, number> = {};
prices['sku-1'].toFixed(2);              // compiles, throws; noUncheckedIndexedAccess -> number | undefined

class Animal { name = '' }
class Dog extends Animal { bark() {} }
class Cat extends Animal { meow() {} }
const dogs: Dog[] = [];
const zoo: Animal[] = dogs;              // allowed (covariant arrays)
zoo.push(new Cat());
dogs[0].bark();                           // runtime TypeError

interface Listener { on(e: Event): void }            // method syntax: bivariant
const l: Listener = { on(e: KeyboardEvent) { e.key; } }; // accepted
interface Listener2 { on: (e: Event) => void }       // property syntax: contravariant, rejects above

const box = { val: 'x' as string | null };
if (box.val !== null) {
  reset(box);                             // sets box.val = null
  box.val.length;                         // still narrowed to string -> throws
}
function reset(b: { val: string | null }) { b.val = null; }
```
Defensive `tsconfig`:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "useUnknownInCatchVariables": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "verbatimModuleSyntax": true
  }
}
```
typescript-eslint: `no-explicit-any`, `no-unsafe-assignment`, `no-unsafe-member-access`, `no-unsafe-call`, `no-unsafe-return`, `no-non-null-assertion`, `consistent-type-assertions` (ban object-literal assertions).

## Trade-offs & pitfalls
- `noUncheckedIndexedAccess` adds friction in loops over arrays; use `for...of`, `.at()` with checks, or tuple types instead of `!` everywhere.
- `exactOptionalPropertyTypes` breaks many third-party typings and spread patterns; expect churn.
- Use property-syntax function types in your own interfaces when you want contravariant checking.
- `ReadonlyArray` in public APIs sidesteps the covariance write hole.
- **Rollout at scale (principal answer)**: it's a migration, not a config flip. Enable per package/directory (project references or per-folder tsconfigs), count violations in CI and allow the number only to go down (ratchet), fix highest-traffic modules first, track `any` density as a code-health metric next to coverage.

## Likely follow-ups
- **Why not make TS sound?** It would reject valid JS patterns (DOM event handlers, mutable arrays) and hurt adoption; the team chose pragmatism, your job is knowing the edges.
- **Third-party `any` types?** Wrap the lib in a small typed adapter, validate outputs that cross a trust boundary, upstream fixes to DefinitelyTyped when worth it.
- **Why are methods bivariant at all?** Largely so common patterns like DOM handler hierarchies and `Array<T>` methods remain assignable; the TS FAQ covers it.
- **How do you measure `any`?** Tools like `type-coverage` report the share of typed identifiers; gate it in CI (verify the tool's current flags).

## Say it in 60 seconds
TypeScript chooses usability over soundness, so there are known holes. `any` from `JSON.parse`, `fetch().json()` or untyped libraries spreads silently. Index access assumes the key exists. Arrays are covariant, so you can push a Cat into an array of Dogs through an Animal alias. Method-syntax parameters are checked bivariantly even under strict function types. And assertions, non-null bangs and narrowings that survive a mutating call all lie. I close what I can with `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and unknown in catch, plus typescript-eslint's no-unsafe rules, readonly arrays in public APIs, and validation at boundaries. In a large codebase I roll that out per package with a CI ratchet on violation counts, starting with the highest-traffic modules, and track any density as a health metric.
