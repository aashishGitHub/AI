# WeakMap, WeakRef and FinalizationRegistry: what problems do they solve, and what are the traps?
**Round:** 01 · JavaScript Internals · **Level:** Lead / Staff · **Time:** 10 min · **Tags:** weakmap · weakref · garbage collection
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Whether you reach for WeakMap by default, treat WeakRef/FinalizationRegistry as rare tools, and refuse to put correctness on GC timing.

## Core answer (key points)
- **WeakMap/WeakSet**: keys held weakly. Attaching data to an object doesn't keep it alive; entry disappears with the key. Right tool for **metadata on objects you don't own** (DOM nodes, third-party objects) and per-identity memoization.
- Keys must be objects (or non-registered symbols). No iteration, no `size`: enumerating would expose GC timing.
- **WeakRef**: hold an object without keeping it alive; `deref()` returns it or `undefined`.
- **FinalizationRegistry**: callback *eventually, maybe* after a registered target is collected.
- GC is non-deterministic, so the latter two are for **opportunistic caches and interop**, never for correctness or releasing external resources.
- Deterministic cleanup belongs to explicit `close()`/`dispose()` or `using` + `Symbol.dispose` (explicit resource management, rolling out across runtimes and TS; check current support).

## Mental model / flow
```
Map<Element, Rect>      : map ──strong──> element   (element lives forever)
WeakMap<Element, Rect>  : map ──weak────> element   (element dies -> entry gone)
Map<K, WeakRef<V>>      : key strong, value weak    (value may vanish any time)
```

## Code sketch
```ts
const rectCache = new WeakMap<Element, DOMRect>();
export function rectOf(el: Element) {
  let r = rectCache.get(el);
  if (!r) rectCache.set(el, (r = el.getBoundingClientRect()));
  return r;
}

class SoftCache<K, V extends object> {
  #map = new Map<K, WeakRef<V>>();
  #gc = new FinalizationRegistry<K>((key) => {
    const ref = this.#map.get(key);
    if (ref && !ref.deref()) this.#map.delete(key); // guard: key may hold a newer live value
  });
  get(k: K) { return this.#map.get(k)?.deref(); }
  set(k: K, v: V) {
    this.#map.set(k, new WeakRef(v));
    this.#gc.register(v, k);   // held value must not be v itself
  }
}
```
Use case: decoded images or parsed documents that are costly to rebuild and fine to drop.

## Trade-offs & pitfalls
- **No timing guarantees**: finalizers may run late, batched, or never (e.g. page unload). Don't close sockets/handles with them.
- `deref()` stability: once deref'd, the engine keeps the target alive until the end of the current job, but the next task may see `undefined`. Always handle disappearance.
- Accidental strong refs defeat weakness: a closure capturing the value, or passing the target as the registry's held value.
- Tests can't reliably observe GC; behaviour differs across engines and runs. Don't write tests that depend on collection.
- A WeakMap value that references its own key still works (ephemeron semantics), but anything *else* holding the key keeps both alive.

## Likely follow-ups
- **How do frameworks use WeakMap?** Vue's reactivity keeps `WeakMap<target, Map<key, Set<effect>>>`; libraries store per-element state for DOM they don't own.
- **Why can't I iterate a WeakMap to debug it?** Live entries depend on GC; exposing them makes programs non-deterministic.
- **WeakMap vs a `Symbol` property on the object?** Symbol mutates the object (visible via `Reflect.ownKeys`, may fail on frozen objects); WeakMap is external and private.
- **When would you actually ship WeakRef?** Rarely: memory-sensitive caches of re-creatable objects, or bridging to non-JS resources as a backstop behind explicit dispose.

## Say it in 60 seconds
WeakMap and WeakSet hold their keys weakly, so you can attach data to an object without keeping it alive, and the entry goes when the object does. That's the everyday tool for metadata on DOM nodes or third-party objects and for identity-keyed memoization; they're deliberately not iterable because that would leak GC timing. WeakRef lets you hold an object without retaining it, and FinalizationRegistry tells you eventually, maybe, that it was collected. I use those only for caches of things that are expensive to rebuild but fine to lose, and I never put correctness or resource release on them, because finalizers can run late or never. Deterministic cleanup is explicit dispose or the new `using` syntax.
