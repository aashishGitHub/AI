# Explain this binding precisely, including arrow functions and class fields
**Round:** 01 · JavaScript Internals · **Level:** Senior · **Time:** 10 min · **Tags:** this · arrow functions · classes
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Can you state the call-site rules and their precedence crisply, diagnose the "method passed as callback" bug in review, and weigh arrow class fields vs prototype methods.

## Core answer (key points)
- `this` is set by **how a function is called**, not where it's defined. Exception: arrows have no own `this`; they read the enclosing scope's.
- Precedence: **`new` > explicit (`call`/`apply`/`bind`) > method call (`obj.fn()`) > default** (`undefined` in strict code/modules/classes, `globalThis` in sloppy scripts).
- `bind` wins over a later `call`; `new` wins over `bind`'s `this` (but keeps bound args).
- `const f = obj.method; f()` → default binding → `undefined` in modules → TypeError on `this.x`.
- `setTimeout(obj.method)` passes a bare function reference; the object is gone. `addEventListener('click', c.inc)` calls it with `this` = the event target.
- Arrow class fields capture the instance at construction, so they survive being passed around.

## Mental model / flow
```
is it an arrow?            -> lexical this (call/bind ignored)
called with new?           -> fresh object
bound / call / apply?      -> that thisArg (first bind wins)
called as obj.fn()?        -> obj
otherwise                  -> undefined (strict) | globalThis (sloppy)
```

## Code sketch
```ts
class Timer {
  ticks = 0;
  tick() { this.ticks++; }                 // on prototype, shared, overridable
  tickBound = () => { this.ticks++; };     // per instance, captures instance
}

const t = new Timer();
setTimeout(t.tick, 0);          // this undefined -> TypeError
setTimeout(t.tickBound, 0);     // works
setTimeout(() => t.tick(), 0);  // works, explicit at call site
```
Nested function vs nested arrow inside a method: the nested `function` gets default binding (`undefined`); the nested arrow sees the method's `this`.

Typed `bind`:
```ts
function bindThis<T, Pre extends unknown[], Rest extends unknown[], R>(
  fn: (this: T, ...a: [...Pre, ...Rest]) => R, self: T, ...pre: Pre
): (...rest: Rest) => R {
  return (...rest) => fn.apply(self, [...pre, ...rest]);
}
```
A spec-complete `bind` also handles being called with `new` (construct instead of call); mention it, don't write it.

## Trade-offs & pitfalls
- Arrow class fields: one function **per instance** (memory), not on the prototype, so subclasses can't call `super.method()` and mocking via prototype doesn't work.
- Arrow as object-literal method (`{ greet: () => this.name }`) reads the outer `this`, not the object.
- Callbacks that accept `thisArg` (`arr.map(fn, ctx)`) set `this` only for non-arrow `fn`.
- Getters/setters receive the receiver (`obj` in `obj.prop`), which matters through prototype chains and `Reflect.get(t, k, receiver)` in proxies.
- Inline `onclick="..."` attributes bind `this` to the element.

## Likely follow-ups
- **Why did React classes need `this.handleClick = this.handleClick.bind(this)`?** JSX passes the method as a plain reference; hooks sidestep `this` entirely.
- **Can you rebind an arrow?** No; `call`/`apply`/`bind` silently ignore the thisArg.
- **What does `obj.method.bind(a).call(b)` give?** `a`; the first bind is final.
- **When is an arrow field the wrong choice?** Large numbers of instances, inheritance/override needs, or prototype-level spying in tests.

## Say it in 60 seconds
`this` is decided at the call site, except for arrow functions, which have no `this` of their own and use the enclosing one. Precedence is `new`, then explicit `call`/`apply`/`bind`, then method call, then default binding, which is `undefined` in modules and classes. So passing `obj.method` to `setTimeout` loses the object because the timer calls a bare function, and an event listener calls it with the element as `this`. Fixes are an arrow class field, binding once, or wrapping in an arrow at the call site. Arrow fields are easy but cost one function per instance and live off the prototype, so you can't override them with `super` or spy on the prototype; for hot, numerous objects I'd keep prototype methods and wrap at the call site.
