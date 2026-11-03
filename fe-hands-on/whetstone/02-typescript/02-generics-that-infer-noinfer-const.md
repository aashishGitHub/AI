# Write generic functions whose types infer correctly: constraints, const type parameters and NoInfer
**Round:** 02 · TypeScript for Real Codebases · **Level:** Senior · **Time:** 15 min · **Tags:** generics · inference · const type parameters
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Designing `pick`, `groupBy`, `createStore` so callers never write type arguments. Today callers write `pick<User, 'id' | 'name'>(user, ['id', 'name'])` and hate it.

Test cases given: `pick(user, ['id','name'])` → `Pick<User,'id'|'name'>` and `'nope'` errors; `groupBy(users, u => u.role)` → record keyed by `Role`; `createStore({ initial: 0, reducers: { inc: s => s + 1 } })` infers state `number`.

## Core answer (key points)
- Good generics are **invisible at the call site**. If callers must pass type args, inference has nothing to infer from: redesign the signature.
- Put type parameters where TS sees **values** (arguments), and **relate** parameters (`K extends keyof T`) instead of widening (`key: string`).
- Constrain only to what you use (`T extends { id: string }`), not to a concrete model.
- **`const` type parameters** (TS 5.0) keep literal types without callers writing `as const`.
- **`NoInfer<T>`** (TS 5.4) stops a parameter from being an inference candidate, so a bad default errors instead of silently widening `T`.
- A type parameter used once is usually not needed (`<T>(x: T): void` is just `x: unknown`).
- When the return type depends on a flag, **overloads** often read better than conditional types.

## Mental model / flow
```
call: pick(user, ['id','name'])
  T  <- from user          (User)
  K  <- from array items   ('id' | 'name'), kept literal because K extends keyof T
  return Pick<T, K>
```

## Code sketch
```ts
function pick<T extends object, K extends keyof T>(obj: T, keys: readonly K[]): Pick<T, K> {
  const out: Partial<Pick<T, K>> = {};
  for (const k of keys) out[k] = obj[k];
  return out as Pick<T, K>;          // contained: loop fills every K
}

function groupBy<T, K extends PropertyKey>(items: readonly T[], keyOf: (item: T) => K) {
  const out: Partial<Record<K, T[]>> = {};
  for (const item of items) (out[keyOf(item)] ??= []).push(item);
  return out;
}

type Reducers<S> = Record<string, (state: S) => S>;
function createStore<S, R extends Reducers<S>>(cfg: { initial: S; reducers: R }) {
  let state = cfg.initial;
  const listeners = new Set<() => void>();
  const actions = Object.fromEntries(
    Object.entries(cfg.reducers).map(([name, fn]) => [name, () => {
      state = fn(state);
      listeners.forEach((l) => l());
    }]),
  ) as { [Name in keyof R]: () => void };
  return { getState: () => state, actions, subscribe: (l: () => void) => (listeners.add(l), () => listeners.delete(l)) };
}

function tabs<const T extends readonly string[]>(ids: T, initial: NoInfer<T[number]>) {
  return { ids, active: initial };
}
tabs(['overview', 'billing'], 'billing');   // ok
tabs(['overview', 'billing'], 'audit');     // error, instead of widening T
```
`groupBy` honestly returns `Partial<Record<K, T[]>>`: a role with no users has no key. If the test insists on `Record<Role, User[]>`, initialise every key from a known list. (`Object.groupBy` in ES2024 is typed with `Partial` in TS's lib, as far as I know; verify for your TS version.)

## Trade-offs & pitfalls
- `createStore` infers `S` from `initial` because the reducer callbacks are context-sensitive and inferred later; if inference picks up a wrong candidate from reducers, wrap the reducer's state type in `NoInfer`.
- `response.json()` returns `Promise<any>`, so a typed fetcher's return "just works" as an unchecked claim; validate at that boundary (see Q06).
- Overloads: implementation signature is not visible to callers; order overloads from most to least specific.
- Generic-heavy helpers can produce unreadable errors; keep them in a utility module with type tests.

## Likely follow-ups
- **Why does `Object.keys` return `string[]`?** Structural typing: runtime objects may carry extra keys, so `(keyof T)[]` would be unsound.
- **What are `in`/`out` variance annotations?** Optional explicit variance on type params for checker performance/clarity in complex library types; rarely needed in apps.
- **Typed fetcher?** `api<P extends keyof Endpoints>(path: P, query: Endpoints[P]['query']): Promise<Endpoints[P]['response']>`; generate `Endpoints` from OpenAPI.
- **`const` type param vs `as const` at call site?** Same result; the former moves the burden from every caller to the author.

## Say it in 60 seconds
A good generic is one the caller never notices: no explicit type arguments, and the result is exactly what they'd expect. I get there by inferring from arguments and relating parameters to each other, so `pick` takes `K extends keyof T` and returns `Pick<T, K>`, which both keeps the keys literal and rejects keys that don't exist. I constrain only to the structure I use. `const` type parameters preserve literal tuples without callers writing `as const`, and `NoInfer` keeps a secondary argument like a default value from becoming an inference site, so a typo errors instead of widening the union. If a type parameter appears once it shouldn't exist, and when a return type depends on a flag, overloads are clearer than conditional types.
