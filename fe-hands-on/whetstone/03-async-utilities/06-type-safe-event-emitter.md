# Implement a type-safe event emitter (on, off, once, error isolation)
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 12 min · **Tags:** event emitter · pub sub · typescript
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
Typed `Emitter<Events>` with `on` returning an unsubscribe, `off`, `once`, safe mutation during `emit`, and one throwing listener not stopping the rest (and not being silently swallowed).

Test cases given: `emit('saved', 42)` is a compile error when `saved` expects `{ id }`; unsubscribe is idempotent; `once` fires exactly once across two emits; listener added during emit doesn't run in that emit, removed one is safe; first of three listeners throws → other two run, error reported.

## Core answer (key points)
- `Map<eventName, Set<listener>>`, typed by an **event map interface** so payloads are checked per event.
- `on` returns `() => off(...)`; `Set.delete` makes double-unsubscribe harmless.
- **Iterate a snapshot** (`[...set]`) so listeners added during emit don't run this time; check `set.has(fn)` before each call so listeners removed mid-emit are skipped.
- `once` wraps the listener; keep a wrapper lookup so `off(event, original)` still works.
- **Error isolation**: try/catch per listener and report asynchronously (rethrow in a microtask, `reportError`, or an `onError` hook) so it reaches error monitoring without breaking the loop.
- One internal cast is unavoidable: a single `Map` can't express "the set for K holds listeners of `Events[K]`". Keep it private behind typed public methods.

## Mental model / flow
```
emit(K, payload)
  snapshot = [...listeners[K]]
  for fn of snapshot:
     if still subscribed -> try fn(payload) catch -> report async
```

## Code sketch
```ts
type Fn<P> = (payload: P) => void;
type Args<P> = [P] extends [void] ? [] : [payload: P];

export class Emitter<E extends object> {
  #subs = new Map<keyof E, Set<Fn<never>>>();
  #onceWrappers = new Map<keyof E, Map<Fn<never>, Fn<never>>>();
  #onError: (err: unknown) => void;

  constructor(onError: (err: unknown) => void = (e) => queueMicrotask(() => { throw e; })) {
    this.#onError = onError;
  }

  on<K extends keyof E>(type: K, fn: Fn<E[K]>): () => void {
    let set = this.#subs.get(type);
    if (!set) this.#subs.set(type, (set = new Set()));
    set.add(fn);
    return () => this.off(type, fn);
  }

  once<K extends keyof E>(type: K, fn: Fn<E[K]>): () => void {
    const wrapper: Fn<E[K]> = (p) => { this.off(type, fn); fn(p); };
    let byOrig = this.#onceWrappers.get(type);
    if (!byOrig) this.#onceWrappers.set(type, (byOrig = new Map()));
    byOrig.set(fn, wrapper);
    this.on(type, wrapper);
    return () => this.off(type, fn);
  }

  off<K extends keyof E>(type: K, fn: Fn<E[K]>): void {
    const wrapper = this.#onceWrappers.get(type)?.get(fn);
    if (wrapper) this.#onceWrappers.get(type)!.delete(fn);
    const set = this.#subs.get(type);
    set?.delete(wrapper ?? fn);
    if (set?.size === 0) this.#subs.delete(type);
  }

  emit<K extends keyof E>(type: K, ...args: Args<E[K]>): void {
    const set = this.#subs.get(type);
    if (!set) return;
    for (const fn of [...set]) {
      if (!set.has(fn)) continue;
      try { (fn as Fn<E[K]>)(args[0] as E[K]); } catch (err) { this.#onError(err); }
    }
  }
}

interface AppEvents { 'doc:saved': { id: string; rev: number }; 'session:expired': void }
const bus = new Emitter<AppEvents>();
const stop = bus.on('doc:saved', ({ id, rev }) => audit(id, rev));
bus.emit('doc:saved', { id: 'a', rev: 2 });
bus.emit('session:expired');
// bus.emit('doc:saved', 42);   // compile error
stop(); stop();                  // harmless
```
`once` calls `off` before invoking, so a re-entrant emit inside the listener can't fire it twice.

## Trade-offs & pitfalls
- **Sync vs async delivery**: sync is predictable and easy to test; async (microtask) avoids re-entrancy surprises when a listener emits another event, but makes ordering less obvious.
- **Leaks**: every `on` needs an owner that calls unsubscribe. Add `on(type, fn, { signal })` so an `AbortController` tears down many subscriptions at once.
- Constrain with `E extends object`, not `Record<string, unknown>`: an `interface` has no implicit index signature, so `interface AppEvents` would fail a `Record` constraint (a `type` alias would pass).
- `Fn<never>` as the storage type accepts any listener (parameter contravariance); the cast lives only in `emit`.
- Silently swallowing listener errors hides bugs; rethrowing synchronously breaks other listeners. Async report is the middle ground.

## Likely follow-ups
- **Should a React app have a global event bus?** Prefer explicit data flow (state, context, query cache). Buses are useful at edges: cross-microfrontend messages, analytics, non-React integrations.
- **Why not just `EventTarget`?** It's built in (`CustomEvent` with `detail`), supports `{ once, signal }`; typing payloads takes a wrapper. Good default in browsers.
- **Wildcard listeners?** Separate `'*'` set receiving `(type, payload)`; type it as a union of `{ type: K; payload: E[K] }`.
- **mitt?** A ~200-byte emitter with the same shape; fine to cite as the production choice.

## Say it in 60 seconds
I map each event name to a Set of listeners and type the class by an event-map interface, so `emit('saved', payload)` checks the payload and events with no payload take no argument. `on` returns an unsubscribe function, and because it's a Set, calling it twice is harmless. `emit` iterates a snapshot so listeners added mid-emit wait for the next one, and checks membership so ones removed mid-emit are skipped. `once` wraps the listener and records the wrapper so you can still `off` it by the original reference. Each listener runs in its own try/catch and errors are reported asynchronously, so one failure doesn't stop the others and isn't swallowed. The only cast is private inside `emit`. In a React app I'd keep buses to the edges and give every subscription an owner.
