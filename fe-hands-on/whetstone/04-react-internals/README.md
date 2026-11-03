# 04 · React Rendering & Internals
> From state change to pixels: render triggers, effects as sync, concurrent rendering, React 19, Server Components, the Compiler · 9 questions · ~2 h 12 min
Source: https://whetstone-v1.vercel.app/#react-internals

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | What exactly happens between setState and pixels on screen? | Senior | 15 min | react · reconciliation · fiber | [notes](01-setstate-to-pixels.md) |
| 02 | When does a component re-render, and which optimizations actually help? | Senior | 15 min | react · rerenders · memo | [notes](02-rerenders-and-optimizations.md) |
| 03 | Effects are synchronization, not lifecycle: when don't you need useEffect? | Senior | 15 min | useeffect · derived state · events | [notes](03-effects-are-synchronization.md) |
| 04 | Transitions, useDeferredValue and Suspense: what does concurrency mean in React? | Lead / Staff | 18 min | concurrent rendering · usetransition · usedeferredvalue | [notes](04-transitions-deferred-suspense.md) |
| 05 | React 19: Actions, useActionState, useOptimistic, use and form handling | Senior | 15 min | react 19 · actions · useactionstate | [notes](05-react19-actions-forms.md) |
| 06 | React Server Components: the mental model, the boundaries and the costs | Lead / Staff | 20 min | rsc · server components · next.js | [notes](06-server-components-model-costs.md) |
| 07 | useSyncExternalStore, tearing, and how state libraries integrate with concurrent React | Lead / Staff | 12 min | usesyncexternalstore · tearing · zustand | [notes](07-usesyncexternalstore-and-tearing.md) |
| 08 | What does the React Compiler change about useMemo, useCallback and how you write components? | Lead / Staff | 10 min | react compiler · memoization · usememo | [notes](08-react-compiler-and-memoization.md) |
| 09 | Stale closures in hooks: how do you diagnose and fix them? | Senior | 12 min | closures · hooks · useref | [notes](09-stale-closures-in-hooks.md) |

## How these connect
- **Spine:** 01 (pipeline) is the base; every other answer references render vs commit, lanes, or purity. Study it first.
- **Performance pair:** 02 (what triggers renders) → 08 (Compiler automates memo) → 04 (when the render is still slow, make it interruptible).
- **Effects cluster:** 03 (fewer effects) + 09 (stale closures in the ones left) + 07 (subscriptions belong in `useSyncExternalStore`, not effects).
- **Concurrency cluster:** 04 (transitions) → 07 (why concurrency causes tearing) → 05 (Actions are transitions with pending/optimistic built in).
- **Architecture closer:** 06 (RSC) reuses Suspense from 04 and Actions/Server Functions from 05; answer it last.
- Suggested order: 01 → 02 → 03 → 09 → 04 → 07 → 05 → 08 → 06.
