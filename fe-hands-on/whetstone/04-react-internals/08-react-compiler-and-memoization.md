# What does the React Compiler change about useMemo, useCallback and how you write components?
**Round:** 04 · React Rendering & Internals · **Level:** Lead / Staff · **Time:** 10 min · **Tags:** react compiler · memoization · usememo
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Lead-level adoption thinking: hundreds of hand-written (some wrong) `useMemo`/`useCallback`; the team wants the Compiler. What does it do, what does it refuse, and what's the rollout plan?

## Core answer (key points)
- **What it is:** a build-time (Babel-based, as I understand it) transform that analyzes components and hooks and inserts fine-grained caching for values, callbacks and JSX elements, keyed on their real dependencies.
- **Effect:** children get stable props and cached elements, so they skip re-rendering — effectively `memo`/`useMemo`/`useCallback` everywhere, without dependency mistakes.
- **Precondition: the Rules of React.** Pure render, no mutation of props/state, no reading/writing refs during render, hooks rules. Code it can't prove safe is **skipped**, not broken (buggy impure code may still behave differently).
- **What it doesn't do:** remove unnecessary effects, fix dependency logic in effects, or fix architecture (colocation, context splitting, virtualization).
- **Escape hatch:** `'use no memo'` directive to opt a component out while debugging.
- **Day-one plan:**
  1. Turn on the compiler-related ESLint rules (in `eslint-plugin-react-hooks`) repo-wide; fix violations.
  2. Enable the compiler on one directory/package (source filter or opt-in annotation mode).
  3. Compare Profiler traces and run E2E; watch code that secretly depended on re-rendering.
  4. Expand gradually; delete manual memo opportunistically, not in one sweep.

## Mental model / flow
```
source component
   │ compiler analysis (rules of React OK?)
   ├─ no  → emitted as-is (bail out), lint tells you why
   └─ yes → cache slots per reactive value:
            visible = cache(todos, filter)
            onToggle = cache()
            <List .../> element = cache(visible, onToggle)
```

## Code sketch
```tsx
// Written plainly — compiler handles memoization
function Inbox({ mails, folder }: { mails: Mail[]; folder: string }) {
  const shown = mails.filter(m => m.folder === folder);
  const onOpen = (id: string) => openMail(id);
  return <MailList items={shown} onOpen={onOpen} />;
}

// Bails out: mutates a prop during render
function Bad({ list }: { list: Item[] }) {
  list.sort(byDate);                // mutation → compiler skips this component
  return <Rows items={list} />;
}
// Fix: const sorted = [...list].sort(byDate);

// Keep manual memo when identity is semantic (external API contract)
const options = useMemo(() => ({ threshold: 0.5 }), []); // passed to a non-React observer lib
```

## Trade-offs & pitfalls
- Code that "worked" because of extra re-renders (reading a mutated object) may change behavior once cached.
- Larger output and some per-component cache overhead; measure bundle and runtime.
- Debugging: stack traces and DevTools show compiled output; know the "memo ✨" badge-style indicators in DevTools (exact UI may vary; verify).
- Status: I believe the Compiler reached a stable 1.0 in late 2025; confirm current version and supported React versions before quoting.

## Likely follow-ups
- **Remove all `useMemo`?** No. Harmless with the compiler; remove opportunistically; keep ones that encode semantic identity (effect deps, external subscriptions) and comment why.
- **Replace `React.memo`?** Effectively, for compiled components.
- **How to prove it helped?** Before/after Profiler commit durations and render counts on key interactions, plus INP from RUM.
- **Works with class components?** No, it targets function components and hooks.

## Say it in 60 seconds
The React Compiler is a build step that inserts fine-grained memoization for values, callbacks and JSX based on their actual dependencies, so most manual `useMemo`, `useCallback` and `memo` become unnecessary and dependency mistakes disappear. It only compiles code that follows the Rules of React; anything impure is skipped. It doesn't fix bad effects or bad architecture. Day one, I'd enable the compiler lint rules and fix violations, turn it on for one package, compare Profiler traces and E2E results, then expand. I'd remove manual memo gradually and keep only memoization that exists for identity reasons, like a stable options object for a non-React library.
