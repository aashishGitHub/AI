# Stale closures in hooks: how do you diagnose and fix them?
**Round:** 04 · React Rendering & Internals · **Level:** Senior · **Time:** 12 min · **Tags:** closures · hooks · useref
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Two bugs: a `setInterval` in `useEffect` always sees `0`; a Save button sometimes saves the previous form values. Do you understand "each render has its own props/state" and pick the right fix per case?

## Core answer (key points)
- Every render is a snapshot: its handlers and effects close over **that render's** props and state.
- A function created in render N but invoked later (timer, socket, memoized callback, `useCallback(fn, [])`) sees render N's values.
- **Fixes, best first:**
  1. **Functional update** — `setCount(c => c + 1)`; the callback no longer needs the value.
  2. **Correct deps** — re-create the callback/effect when the value changes (correct, but may churn: interval re-created each tick).
  3. **`useEffectEvent`** — effect logic that reads latest values without making them deps (reconnect on `roomId`, not on `theme`).
  4. **Latest ref** — `ref.current = value` in a layout effect; read the ref in the callback. The pre-`useEffectEvent` pattern.
  5. **Restructure** — pass values as arguments (`onSave(formValues)`) instead of closing over them.
- **Save-button case:** typically a memoized handler with missing deps, or a handler reading state right after `setState` in the same event (state updates are not visible until next render). Fix with correct deps, or compute next state locally and pass it.

## Mental model / flow
```
render 1: count=0  → effect creates interval, closure{count:0}
render 2: count=1  → effect NOT re-run ([] deps), interval still closure{count:0}
tick: setCount(0+1) → 1 forever
```

## Code sketch
```tsx
// Bug
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000); // count frozen at 0
  return () => clearInterval(id);
}, []);

// Fix 1: functional update
useEffect(() => {
  const id = setInterval(() => setCount(c => c + 1), 1000);
  return () => clearInterval(id);
}, []);

// Fix 3: effect event — reconnect per room, read latest theme
function Room({ roomId, theme }: { roomId: string; theme: Theme }) {
  const onReady = useEffectEvent(() => notify('Connected', theme));
  useEffect(() => {
    const conn = connect(roomId);
    conn.on('ready', onReady);
    return () => conn.close();
  }, [roomId]);
}

// Fix 4: latest ref helper
function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => { ref.current = value; });
  return ref;
}

// Save-button bug and fix
function Form() {
  const [values, setValues] = useState(initial);
  const save = useCallback(() => api.save(values), []); // stale: always initial
  const saveFixed = useCallback(() => api.save(values), [values]);
}
```

## Trade-offs & pitfalls
- Refs everywhere bypass React's data flow and don't trigger renders; use them for values *read in callbacks*, never for values *rendered*.
- `// eslint-disable-next-line react-hooks/exhaustive-deps` nearby is a bug report.
- `exhaustive-deps` can't see values read through refs or closures passed into third-party code; it also can't tell you a dep is semantically wrong.
- Class components had the inverse bug: `this.props` was always latest, even when you wanted the values from the render where the event happened.

## Likely follow-ups
- **Why not refs for everything?** Recreates mutable-state bugs hooks were designed to prevent; rendering from refs goes stale.
- **Is this a React problem?** No, it's JavaScript closures; hooks just make snapshots explicit.
- **Spot it in review?** Values "frozen" in timers/sockets/listeners; `useCallback(..., [])` that reads state; suppressed lint.
- **Does the React Compiler fix it?** No; it respects deps, it doesn't change closure semantics.

## Say it in 60 seconds
Each render closes over its own props and state, so a callback created earlier and called later, like an interval or socket handler, sees old values. For the interval stuck at zero, I'd use a functional update so the callback doesn't need `count` at all. If an effect genuinely needs a fresh value without re-subscribing, I use `useEffectEvent`, or the older latest-ref pattern. The Save bug is usually a `useCallback` with missing deps or reading state right after setting it; I fix the deps or pass the values explicitly. In review I look for frozen values in timers and listeners, empty-dep callbacks that read state, and any disabled `exhaustive-deps` comment.
