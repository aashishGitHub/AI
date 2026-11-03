# 01 · JavaScript Internals
> The runtime underneath every framework: scheduling, memory, `this`, prototypes, modules and meta-programming · 8 questions · ~1 h 44 min
Source: https://whetstone-v1.vercel.app/#javascript-internals

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Walk through the event loop: tasks, microtasks, and where rendering fits | Senior | 15 min | event loop · microtasks · rendering | [notes](01-event-loop-tasks-microtasks-rendering.md) |
| 02 | How do closures cause memory leaks in a long-lived SPA, and how do you find them? | Senior | 15 min | closures · memory · garbage collection | [notes](02-closure-memory-leaks-in-spa.md) |
| 03 | Explain this binding precisely, including arrow functions and class fields | Senior | 10 min | this · arrow functions · classes | [notes](03-this-binding-arrows-class-fields.md) |
| 04 | How do prototypes, classes and private fields actually work under the hood? | Senior | 12 min | prototypes · classes · private fields | [notes](04-prototypes-classes-private-fields.md) |
| 05 | ESM vs CommonJS: live bindings, cycles, tree shaking and interop | Lead / Staff | 15 min | modules · esm · commonjs | [notes](05-esm-vs-commonjs.md) |
| 06 | Iterators, generators and async iterators: when do they earn their place in UI code? | Senior | 12 min | iterators · generators · async iterators | [notes](06-iterators-generators-async-iterators.md) |
| 07 | WeakMap, WeakRef and FinalizationRegistry: what problems do they solve, and what are the traps? | Lead / Staff | 10 min | weakmap · weakref · garbage collection | [notes](07-weakmap-weakref-finalizationregistry.md) |
| 08 | Build a tiny reactive store with Proxy. What are the limits? | Lead / Staff | 15 min | proxy · reflect · reactivity | [notes](08-reactive-store-with-proxy.md) |

## How these connect
- **Scheduling (01)** is the base layer: microtasks vs tasks vs the render step explain frozen spinners, React's time slicing and why `await` always defers. Read it first.
- **Reachability (02, 07)** pair up: 02 is "how closures keep things alive and how to prove it in DevTools"; 07 is the toolbox (WeakMap good, WeakRef/FinalizationRegistry rarely) for not keeping things alive.
- **Object model (03, 04)** pair up: call-site `this` rules, then the prototype chain, `new`, `super` and `#private` brand checks. 04's Proxy/private-field gotcha sets up 08.
- **Modules (05)** stands alone but is the one most likely at Lead/Staff level: live bindings, cycles, tree shaking, dual-package hazard, design-system packaging.
- **Laziness and interception (06, 08)**: generators for pull-based, cancellable pipelines; Proxy + Reflect for push-based fine-grained reactivity. 08 reuses WeakMap from 07 and receiver semantics from 03.
- Suggested order: 01 → 03 → 04 → 02 → 07 → 08 → 06 → 05.
