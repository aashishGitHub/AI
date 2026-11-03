# How do prototypes, classes and private fields actually work under the hood?
**Round:** 01 · JavaScript Internals · **Level:** Senior · **Time:** 12 min · **Tags:** prototypes · classes · private fields
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
That you know `class` is mostly sugar *with real semantic differences*, can narrate `new` step by step, and understand `#private` as brand-checked per-instance slots, not properties.

## Core answer (key points)
- Every object has an internal `[[Prototype]]`; property reads walk the chain until found or `null`.
- `class B extends A` wires two chains: `B.prototype → A.prototype` (instances) and `B → A` (statics).
- `super.m()` looks up from the method's **home object's** prototype, not from `this`'s prototype, so it works even for borrowed methods.
- Real class vs constructor-function differences: class bodies are strict, classes throw if called without `new`, methods are non-enumerable, `super`/`[[HomeObject]]` semantics, derived constructors have no `this` until `super()` returns, TDZ for the class binding.
- `#field`: stored per instance, invisible to `Object.keys`, `JSON.stringify`, `Reflect.ownKeys` and proxies; reading it on a foreign object throws (brand check); `#x in obj` tests safely.
- TypeScript `private` is compile-time only; at runtime it's a normal property.

## Mental model / flow
`new Derived(args)`:
1. Base-most constructor allocates the object with `[[Prototype]] = Derived.prototype`.
2. Derived constructor runs; `this` is unavailable until `super()` returns.
3. Base fields initialise during base construction; derived fields initialise right after `super()` returns.
4. Result is the object, unless the constructor explicitly returns another object.

```
rex ──[[Prototype]]──> Dog.prototype ──> Animal.prototype ──> Object.prototype ──> null
Dog ──[[Prototype]]──> Animal   (static inheritance)
```

## Code sketch
```ts
class Token {
  #raw: string;
  constructor(raw: string) { this.#raw = raw; }
  static is(v: unknown): v is Token {
    return typeof v === 'object' && v !== null && #raw in v;
  }
  equals(other: Token) { return this.#raw === other.#raw; } // throws if other lacks the brand
}

class HttpError extends Error {
  status: number;
  constructor(message: string, status: number, opts?: { cause?: unknown }) {
    super(message, opts);
    this.name = 'HttpError';
    this.status = status;   // explicit assignment, no TS parameter property
  }
}
```

## Trade-offs & pitfalls
- **Proxy + private fields**: a method called through a proxy gets `this = proxy`, which lacks the brand → TypeError. Real issue for proxy-based reactivity.
- Transpiled classes (older Babel/TS targets) emulate privates with WeakMaps and may differ from native on edge cases (enumerability, `super` calls, `new.target`). I'm not certain of every difference per toolchain version; check your target.
- TS parameter properties (`constructor(readonly status: number)`) are non-erasable syntax; projects using `erasableSyntaxOnly` or Node type stripping forbid them.
- Deep UI class hierarchies age badly; one level (`extends Error`) is fine, otherwise compose.

## Likely follow-ups
- **Why is `instanceof` unreliable across iframes or duplicated packages?** It compares against one specific `Ctor.prototype`; two realms or two package copies mean two prototypes. Use brand checks or `Symbol.for` tags.
- **Why `Object.create(null)`?** Dictionary with no prototype so `__proto__`/`constructor` keys can't collide; `Map` is usually better.
- **What is prototype pollution?** Unsafe deep merge writes into `Object.prototype` via a `__proto__` key; block `__proto__`, `constructor`, `prototype` keys.
- **Are private methods inherited?** Subclass instances have the base's private slots (base constructor installs them), but subclass code can't name them.

## Say it in 60 seconds
Objects link to a prototype and lookups walk that chain. `class B extends A` sets `B.prototype`'s prototype to `A.prototype` and `B`'s prototype to `A`, so both instance and static members inherit. `new` allocates an object linked to the constructor's prototype, runs the constructor, initialises fields, and returns it; in a derived class `this` doesn't exist until `super()` returns, because the base allocates it. Classes are mostly sugar but differ for real: strict, must use `new`, home-object `super`. Private `#fields` aren't properties at all; they're per-instance slots guarded by a brand check, invisible to reflection, and they break when a method runs through a Proxy. TypeScript's `private` is just a compile-time label.
