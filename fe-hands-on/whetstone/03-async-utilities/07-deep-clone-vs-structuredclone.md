# Deep clone with cycles, Map, Set and Date, and when to just use structuredClone
**Round:** 03 · Async Patterns & JS Machine Coding · **Level:** Senior · **Time:** 12 min · **Tags:** deep clone · structuredclone · recursion
Source: https://whetstone-v1.vercel.app/#async-utilities

## What they're really testing
A correct recursive clone (cycles, shared refs, built-ins), a clear statement of what it does with functions/classes/DOM, and the judgement that you usually shouldn't deep clone at all.

Test cases given: `a.self = a` → `b.self === b`, `b !== a`; Map with object keys and Set values cloned independently; Date clone is a new object with same time; mutating the original array doesn't affect the copy; explain functions, class instances, DOM vs `structuredClone`.

## Core answer (key points)
- **Production default: `structuredClone`**. Handles cycles, Map, Set, Date, RegExp, ArrayBuffer/typed arrays, Blob/File, Error types. Does **not** handle functions or DOM nodes (throws `DataCloneError`), drops prototypes (class instances become plain objects), ignores symbol keys, drops getters (copies values), loses property descriptors.
- Hand-rolled: recurse with a **`WeakMap<original, copy>`**, registered *before* recursing into children. That handles both cycles and shared references.
- Switch on type for built-ins (Date, RegExp, Map, Set, Array), else create with the **same prototype** and copy own property descriptors (`Reflect.ownKeys` includes symbols).
- Functions and DOM nodes: copy by reference (and say so).

## Mental model / flow
```
clone(v):
  primitive/function -> return v
  seen.has(v)        -> return seen.get(v)       // cycle or shared ref
  built-in?          -> construct copy, seen.set, fill children recursively
  plain/class object -> Object.create(proto), seen.set, copy descriptors with cloned values
```

## Code sketch
```ts
export function deepClone<T>(input: T): T {
  const seen = new WeakMap<object, unknown>();

  const walk = (v: unknown): unknown => {
    if (typeof v !== 'object' || v === null) return v;
    if (seen.has(v)) return seen.get(v);

    if (v instanceof Date) return new Date(v.getTime());
    if (v instanceof RegExp) return new RegExp(v.source, v.flags);
    if (ArrayBuffer.isView(v) && !(v instanceof DataView)) return (v as unknown as { slice(): unknown }).slice();

    if (v instanceof Map) {
      const m = new Map();
      seen.set(v, m);
      for (const [k, val] of v) m.set(walk(k), walk(val));
      return m;
    }
    if (v instanceof Set) {
      const s = new Set();
      seen.set(v, s);
      for (const val of v) s.add(walk(val));
      return s;
    }
    if (Array.isArray(v)) {
      const arr: unknown[] = [];
      seen.set(v, arr);
      v.forEach((item, i) => { arr[i] = walk(item); });
      return arr;
    }

    const out = Object.create(Object.getPrototypeOf(v));
    seen.set(v, out);
    for (const key of Reflect.ownKeys(v)) {
      const desc = Object.getOwnPropertyDescriptor(v, key)!;
      if ('value' in desc) desc.value = walk(desc.value);
      Object.defineProperty(out, key, desc);
    }
    return out;
  };

  return walk(input) as T;   // contained: runtime shape changes the type system can't follow
}
```

| Approach | Cycles | Map/Set/Date | Prototype | Functions |
|---|---|---|---|---|
| `JSON.parse(JSON.stringify(x))` | throws | lost (Date → string, Map → `{}`) | lost | dropped |
| `structuredClone(x)` | yes | yes | lost | throws |
| custom (above) | yes | yes | kept | shared by ref |
| Immer / structural sharing | n/a | yes | yes | n/a, copies only changed path |

## Trade-offs & pitfalls
- **Usually the wrong tool in React/Redux**: deep cloning breaks referential equality everywhere, so every memoised selector and `React.memo` recomputes. Use structural sharing (`{ ...s, user: { ...s.user, name } }`) or Immer's `produce`.
- Very deep structures overflow the stack; use an explicit work stack for adversarial input.
- Copying accessor descriptors keeps getters that may close over the *original* object.
- Frozen/non-writable descriptors are copied as-is; decide whether the copy should be frozen.
- Class instances with `#private` fields: `Object.create(proto)` produces an object *without* the private slots, so methods will throw on brand checks. Mention it; a generic clone can't fix that.
- `DataView`, `Blob`, `File`, `Error` need special cases if you care; `structuredClone` already has them.

## Likely follow-ups
- **Why register in `seen` before recursing?** So a child pointing back to the parent finds the in-progress copy instead of recursing forever.
- **`structuredClone` and transfer?** `structuredClone(buf, { transfer: [buf] })` moves an ArrayBuffer instead of copying (original becomes detached).
- **Where else is structured clone used?** `postMessage` to workers/iframes, IndexedDB, `history.pushState` state.
- **Deep equality?** Same traversal shape with a pair-wise seen map; or rely on immutability + reference checks.

## Say it in 60 seconds
In production I'd call `structuredClone`: it handles cycles, Map, Set, Date, RegExp, typed arrays and blobs, but it throws on functions and DOM nodes and returns plain objects for class instances. If asked to write one, I recurse with a WeakMap from original to copy, registering each copy before visiting its children, which handles both cycles and shared references. I special-case Date, RegExp, typed arrays, Map, Set and arrays, and for everything else create an object with the same prototype and copy own property descriptors, including symbol keys. Functions stay shared by reference. Then I'd push back on the premise: in React or Redux deep cloning state breaks referential equality and defeats every memo, so structural sharing or Immer is almost always what you actually want.
