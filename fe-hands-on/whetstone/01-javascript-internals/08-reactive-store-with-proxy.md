# Build a tiny reactive store with Proxy. What are the limits?
**Round:** 01 · JavaScript Internals · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** proxy · reflect · reactivity
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Implementing `reactive(obj)` + `effect(fn)` (Vue 3 style): track in `get`, trigger in `set`/`deleteProperty`, lazy deep proxies, no-op on same value, and naming the real-world limits.

Test cases given: effect logs `[0, 1]` after `count++`; writing the same value twice runs once; an effect reading only `a` ignores `b`; nested `state.user.name` writes re-run readers.

## Core answer (key points)
- `deps: WeakMap<target, Map<key, Set<effect>>>`. A module-level `activeEffect` marks who is reading.
- `get` → `track(target, key)` then return the value; wrap object values in `reactive()` lazily.
- `set` → compare old/new with `Object.is`; only `trigger` on real change.
- `deleteProperty` → trigger if the key existed.
- Cache proxies in a `WeakMap<raw, proxy>` so the same raw object always yields the same proxy.
- Use **`Reflect` with `receiver`** so getters run with `this = proxy` and their inner reads are tracked too.
- Copy the effect set before iterating in `trigger`: effects re-subscribe while running.

## Mental model / flow
```
effect(fn) ─ sets activeEffect ─► fn() reads state.x ─► get trap ─► track(raw, 'x')
state.x = 2 ─► set trap ─► changed? ─► trigger(raw, 'x') ─► re-run effects for 'x'
```

## Code sketch
```ts
type Fx = () => void;
const graph = new WeakMap<object, Map<PropertyKey, Set<Fx>>>();
const cache = new WeakMap<object, object>();
let current: Fx | null = null;

const subs = (t: object, k: PropertyKey) => {
  let byKey = graph.get(t) ?? graph.set(t, new Map()).get(t)!;
  return byKey.get(k) ?? byKey.set(k, new Set()).get(k)!;
};

export function reactive<T extends object>(raw: T): T {
  const hit = cache.get(raw);
  if (hit) return hit as T;               // the one contained assertion
  const p = new Proxy(raw, {
    get(t, k, r) {
      if (current) subs(t, k).add(current);
      const v = Reflect.get(t, k, r);
      return v !== null && typeof v === 'object' ? reactive(v) : v;
    },
    set(t, k, v, r) {
      const prev = Reflect.get(t, k, r);
      const ok = Reflect.set(t, k, v, r);
      if (ok && !Object.is(prev, v)) [...(graph.get(t)?.get(k) ?? [])].forEach((f) => f());
      return ok;
    },
    deleteProperty(t, k) {
      const had = Reflect.has(t, k);
      const ok = Reflect.deleteProperty(t, k);
      if (ok && had) [...(graph.get(t)?.get(k) ?? [])].forEach((f) => f());
      return ok;
    },
  });
  cache.set(raw, p);
  return p;
}

export function effect(fn: Fx) {
  const run: Fx = () => {
    const prev = current;
    current = run;
    try { fn(); } finally { current = prev; }
  };
  run();
}
```
Self-write loop guard (an effect that writes a key it reads): skip triggering `current` from inside itself, or schedule effects. The toy above doesn't guard; mention it.

## Trade-offs & pitfalls
- **Stale deps**: toy never removes an effect from keys it stopped reading after a branch flips. Real systems clear an effect's deps before each run.
- **Arrays**: `push` touches `length` and indices; track `length` and avoid read-write loops.
- **Built-ins with internal slots** (`Map`, `Set`, `Date`, typed arrays) throw when methods run with `this = proxy`; libraries wrap them with collection handlers.
- **`#private` fields** fail the brand check when methods run on the proxy.
- **Identity**: `reactive(o) !== o`; mixing raw and proxied objects, or leaking proxies to third-party code, causes subtle bugs.
- **Batching**: three writes = three runs; real systems schedule in a microtask and dedupe.
- **Performance**: every read goes through a trap; mark large data tables as raw.

## Likely follow-ups
- **Proxy reactivity vs signals vs React?** React re-renders and diffs (coarse, predictable, no tracking). Proxies/signals track fine-grained reads and update exactly the dependents. Signals make tracking explicit (`count()`), avoiding proxy edge cases.
- **Integrate with React?** Expose `subscribe` + `getSnapshot`, return immutable snapshots, consume via `useSyncExternalStore` (Valtio's `useSnapshot` works this way).
- **Why WeakMap for `graph`?** Dropping the raw state object drops its dependency map too.
- **How would you add computed?** A lazy effect with a dirty flag that triggers its own readers when a dependency changes.

## Say it in 60 seconds
A Proxy intercepts get, set and delete. I keep a WeakMap from raw object to key to set of effects and a global "currently running effect". The get trap records that the active effect read that key and lazily wraps nested objects; the set trap writes via Reflect, compares with `Object.is`, and only re-runs subscribers if the value actually changed; delete triggers if the key existed. Reflect with the receiver matters so getters run against the proxy and their reads are tracked. The limits are what make real libraries big: stale dependencies after branches change, array length tracking, Map/Set/Date internal slots, private fields failing brand checks through proxies, proxy identity not equal to the raw object, no batching, and trap overhead on hot reads. Signals are the same idea with explicit getters.
