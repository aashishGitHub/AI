# Model your data so you never need as: unions, narrowing, type guards and satisfies
**Round:** 02 · TypeScript for Real Codebases · **Level:** Senior · **Time:** 15 min · **Tags:** narrowing · type guards · satisfies
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Can you remove `as` and `!` from a reducer and API layer *without* losing safety, by changing the data model and moving runtime questions to runtime checks.

Test cases given: reading `state.data` while `loading` is a compile error; a `switch` missing a case fails exhaustiveness; a `satisfies Record<string, string>` config keeps literal key/value types.

## Core answer (key points)
- `as` means "trust me": checking stops there and the bug surfaces far from the cause (`JSON.parse(raw) as User`).
- Four replacements:
  1. **Discriminated unions** for state, so impossible combos can't be constructed.
  2. **`unknown` at the edge** + real narrowing (`typeof`, `instanceof`, `in`, equality, `Array.isArray`, control flow).
  3. **Type predicates** (`v is User`) and **assertion functions** (`asserts v is User`) for reusable checks.
  4. **`satisfies`** to validate a literal against a type without widening it.
- `as const` is fine: it narrows, it doesn't lie.
- Keep the irreducible assertions in small, tested adapter modules.
- TS 5.5+ infers predicates for simple arrows (`.filter(x => x !== null)` gives `number[]`).

## Mental model / flow
```
external input (fetch, storage, DOM)  ──► unknown
        │ narrow / predicate / schema
        ▼
domain types (unions)  ──► switch on tag ──► assertNever default
```

## Code sketch
```ts
type Remote<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; message: string };

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

interface Me { id: string; email: string | null }
function isMe(v: unknown): v is Me {
  return isObj(v) && typeof v.id === 'string' && (v.email === null || typeof v.email === 'string');
}

const body: unknown = await res.json();
if (!isMe(body)) throw new Error('Unexpected /me payload');

const btn = document.querySelector('#save');
if (btn instanceof HTMLButtonElement) btn.disabled = true;   // runtime check, not a cast

const theme = {
  primary: '#0a5',
  danger: '#d33',
} satisfies Record<string, `#${string}`>;
type ThemeKey = keyof typeof theme;   // 'primary' | 'danger', not string
```
Annotation (`const theme: Record<string, ...>`) would widen keys to `string`; `as` would skip checking entirely.

## Trade-offs & pitfalls
- **A predicate is itself a trusted claim**: `(v): v is User => true` compiles. Keep them tiny and tested, or derive them from a schema so check and type can't drift.
- Non-null `!` is an assertion too; prefer an explicit check that throws a useful message.
- `Object.entries`/`Object.keys` lose key types by design; write one typed helper in a utility module instead of casting everywhere.
- `querySelector<HTMLInputElement>()` and `useRef<HTMLInputElement>(null)` are conventional, scoped claims; acceptable.
- Optional-field soup (`loading?`, `data?`, `error?`) is the root cause of most casts; fix the model first.

## Likely follow-ups
- **When is `as` acceptable?** Adapters where TS can't express a proven invariant (WeakMap caches keyed by object), partial test fixtures, mid-migration JS. Localise, explain why, test it.
- **`unknown` vs `any`?** `unknown` forces narrowing; `any` disables checking and spreads silently. Enable `noImplicitAny`, `useUnknownInCatchVariables`, lint `no-explicit-any`/`no-unsafe-*`.
- **Assertion function vs predicate?** Assertion throws and narrows the rest of the scope; good at boundaries and in tests.
- **How does `satisfies` interact with `as const`?** `as const satisfies T` gives readonly literals that are still checked against `T`.

## Say it in 60 seconds
An `as` cast turns a runtime question into an unchecked claim, so the crash shows up far from the cause. I remove them by fixing the model: request state becomes a discriminated union so `data` only exists in the success branch, and a switch with an `assertNever` default makes missing cases a compile error. External data comes in as `unknown` and gets narrowed with real checks or a type predicate, ideally generated from a schema so the check and the type can't drift, because a predicate is itself a trusted claim. For config objects I use `satisfies`, which validates against a type but keeps the literal keys and values. The few assertions that remain live in small, tested adapter modules.
