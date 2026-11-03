# Conditional types, infer and mapped types: build DeepReadonly, PathValue and a typed event map
**Round:** 02 · TypeScript for Real Codebases · **Level:** Lead / Staff · **Time:** 20 min · **Tags:** conditional types · infer · mapped types
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Fluency with the type-level toolkit, proof via type tests, and the judgement to contain it.

Test cases given: `DeepReadonly<{ a: { b: string[] } }>` blocks `x.a.b.push()`; `PathValue<{ user: { age: number } }, 'user.age'>` is `number` and a bad path errors; `emit('saved', 42)` fails when `saved` expects `{ id: string }`; explain distribution and `infer`.

## Core answer (key points)
- **Conditional types** `T extends U ? X : Y` are type-level `if`. They **distribute over unions** when `T` is a naked type parameter; wrap in a tuple (`[T] extends [U]`) to stop it.
- **`infer`** captures a piece of a matched type (promise payload, array element, function params/return).
- **Mapped types** `{ [K in keyof T]: ... }` transform each property; `as` clause remaps or filters keys.
- **Template literal types** build string unions (`on${Capitalize<K>}Change`, dotted paths).
- Combine: recursion + `infer` on template literals = `PathValue`.
- Always ship with **type tests** (`Expect<Equal<...>>`, Vitest `expectTypeOf`, tsd).

## Mental model / flow
`PathValue<T, 'user.address.city'>`:
```
'user.address.city' matches `${H}.${R}` -> H='user', R='address.city' -> recurse on T['user']
'address.city'      matches             -> H='address', R='city'      -> recurse
'city'              no dot              -> 'city' extends keyof T ? T['city'] : never
```

## Code sketch
```ts
type Box<T> = T extends unknown ? T[] : never;        // Box<string|number> = string[] | number[]
type BoxAll<T> = [T] extends [unknown] ? T[] : never; // (string|number)[]

type Unwrap<T> = T extends PromiseLike<infer V> ? Unwrap<V> : T;
type Item<T> = T extends readonly (infer E)[] ? E : never;
type FirstArg<F> = F extends (a: infer A, ...rest: never[]) => unknown ? A : never;

type DeepReadonly<T> =
  T extends (...a: never[]) => unknown ? T :
  T extends ReadonlyMap<infer K, infer V> ? ReadonlyMap<DeepReadonly<K>, DeepReadonly<V>> :
  T extends ReadonlySet<infer V> ? ReadonlySet<DeepReadonly<V>> :
  T extends object ? { readonly [K in keyof T]: DeepReadonly<T[K]> } :
  T;
// arrays: homomorphic mapped types over arrays produce readonly arrays, so push() disappears

type Leaf = string | number | boolean | bigint | symbol | null | undefined | Date;
type Path<T> = T extends Leaf ? never : {
  [K in keyof T & string]: T[K] extends Leaf ? K : K | `${K}.${Path<T[K]>}`;
}[keyof T & string];

type PathValue<T, P extends string> =
  P extends `${infer H}.${infer R}` ? (H extends keyof T ? PathValue<T[H], R> : never) :
  P extends keyof T ? T[P] : never;

type EventMap = { saved: { id: string }; closed: void };
declare function emit<K extends keyof EventMap>(
  type: K,
  ...args: EventMap[K] extends void ? [] : [payload: EventMap[K]]
): void;
emit('saved', { id: 'a' }); // ok
emit('closed');             // ok, no payload
// emit('saved', 42);       // error

type Handlers<T> = { [K in keyof T & string as `on${Capitalize<K>}Change`]: (v: T[K]) => void };

type Equal<X, Y> = (<G>() => G extends X ? 1 : 2) extends (<G>() => G extends Y ? 1 : 2) ? true : false;
type Expect<T extends true> = T;
type _t = [Expect<Equal<PathValue<{ user: { age: number } }, 'user.age'>, number>>];
```
`register<P extends Path<Form>>(name: P): PathValue<Form, P>` is roughly how form libraries (react-hook-form) type field names.

## Trade-offs & pitfalls
- Compile-time cost: deep recursion over big models slows `tsc` and editors, and can hit "Type instantiation is excessively deep and possibly infinite". TS has limits (tail-recursive conditional types get a much higher cap than non-tail ones); exact numbers vary by version, verify before quoting.
- Error messages from these types are hostile; product engineers can't debug them.
- `Path<T>` on recursive types (tree nodes) explodes; add a depth counter tuple or stop at known leaves.
- `Equal` via the generic-function trick is a community idiom; it's stricter than mutual assignability (distinguishes `any`).
- Principal framing: keep heavy types behind a few library boundaries (forms, API client, router), expose simple types to product code, profile with `tsc --extendedDiagnostics` / `--generateTrace`.

## Likely follow-ups
- **Why does distribution happen?** Conditional types over a naked type parameter are applied per union member by design; it's what makes `Exclude`/`Extract` work.
- **How do you debug a complex type?** Hover, split into intermediate aliases, flatten with `type Prettify<T> = { [K in keyof T]: T[K] } & {}`.
- **How does `as` in a mapped type filter keys?** Map a key to `never` and it's dropped (`as T[K] extends Function ? never : K`).
- **`infer` with constraints?** `infer U extends string` narrows what's captured (TS 4.7+).

## Say it in 60 seconds
Conditional types are if-statements on types and distribute across unions when the checked type is a bare type parameter, which you turn off by wrapping both sides in a tuple. `infer` pulls a piece out of a matched shape, like a promise's value or a function's first argument. Mapped types transform every property and can rename or drop keys with an `as` clause, and template literal types build string unions. DeepReadonly is a recursive mapped type that skips functions and special-cases Map and Set. PathValue splits a dotted string with `infer` on a template literal and recurses, and a typed emitter uses a rest tuple so events without payloads take no argument. I always prove these with `Expect<Equal>` tests, and I keep them inside a few library boundaries because they cost compile time and produce errors product engineers can't read.
