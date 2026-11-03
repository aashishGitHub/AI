# React 19: Actions, useActionState, useOptimistic, use and form handling
**Round:** 04 · React Rendering & Internals · **Level:** Senior · **Time:** 15 min · **Tags:** react 19 · actions · useactionstate
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Can you build a "rename project" form that feels instant (optimistic name, disabled button, rollback, server validation message) with React 19 primitives instead of hand-rolled `isLoading` state, and do you know each hook's responsibility?

## Core answer (key points)
- **Action** = an async function React runs inside a transition. React tracks pending, errors and ordering of submissions.
- **`useActionState(fn, initial)`** → `[state, dispatch, isPending]`. `fn(prevState, formData)` returns the next state; ideal for returning validation errors as data.
- **`<form action={dispatch}>`** submits via the action; with Server Functions it can work before JS loads (progressive enhancement).
- **`useFormStatus()`** lets a nested submit button read its parent form's pending state without props. Must be inside the `<form>`.
- **`useOptimistic(value, reducer)`** shows a temporary value while the action runs; it snaps back to the real value when the transition ends (success or failure). You still surface the error yourself.
- **`use(promise)`** reads a promise in render, suspending until resolved; may be called conditionally. Promise must be stable (cached / from a Server Component), never created in render.
- Other 19 changes: `ref` is a plain prop on function components; ref callbacks can return cleanup; `<Context>` works as provider; `<title>/<meta>/<link>` hoist to head; `preload/preinit/preconnect`; better hydration diagnostics.
- Still needs a library: caching, retries, dedupe, complex client validation/field arrays.

## Mental model / flow
```
submit → dispatch(formData) inside a transition
   ├─ addOptimistic(newName)  → UI shows new name immediately
   ├─ useFormStatus.pending   → button disabled
   ├─ await server
   │     ok    → return {status:'saved'}  → real prop updates, optimistic dropped
   │     error → return {status:'error',msg} → optimistic dropped (rollback), msg shown
   └─ isPending false
```

## Code sketch
```tsx
type RenameState = { ok: true } | { ok: false; error: string } | null;

function RenameProject({ project }: { project: Project }) {
  const [shownName, setOptimisticName] = useOptimistic(project.name);
  const [state, dispatch] = useActionState<RenameState, FormData>(async (_prev, fd) => {
    const name = String(fd.get('name') ?? '').trim();
    if (name.length < 2) return { ok: false, error: 'Too short' };
    setOptimisticName(name);
    const res = await api.renameProject(project.id, name);
    return res.ok ? { ok: true } : { ok: false, error: res.message };
  }, null);

  return (
    <form action={dispatch}>
      <h2>{shownName}</h2>
      <label htmlFor="pname">Project name</label>
      <input id="pname" name="name" defaultValue={project.name} aria-describedby="pname-msg" />
      <Save />
      <p id="pname-msg" role="status">{state && !state.ok ? state.error : ''}</p>
    </form>
  );
}

function Save() {
  const { pending } = useFormStatus();
  return <button disabled={pending}>{pending ? 'Saving…' : 'Save'}</button>;
}
```
(I am not fully certain the exact generic signature of `useActionState` in TS typings; check `@types/react`.)

## Trade-offs & pitfalls
- React resets uncontrolled fields after a successful action submit. Great for "add comment", surprising for edit forms; derive `defaultValue` from returned state or use controlled inputs.
- Optimistic rollback is silent; always render an error.
- Thrown errors inside actions go to the nearest error boundary; returning error state is usually friendlier for validation.
- Overlapping submits are queued/sequenced by React; design server idempotency anyway.
- `use()` with a promise created in render → suspends forever (new promise each render).

## Likely follow-ups
- **Action vs `async onClick`?** Actions run in transitions: pending tracking, sequencing, Suspense/error-boundary integration, server function wiring. A plain handler gives none.
- **Still use react-hook-form?** For complex validation, field arrays, dirty tracking, yes (can submit through an action). Simple forms: `useActionState` + native validation.
- **Where does `useFormStatus` not work?** In the component that renders the `<form>` itself; it reads the nearest *parent* form.
- **Server Functions security?** They're public endpoints: authenticate, authorize, validate every call.

## Say it in 60 seconds
React 19 makes async mutations first-class. An Action is an async function run in a transition, so React tracks pending state, errors and ordering for me. `useActionState` wraps it and returns the latest result, which is where I return server validation messages. The form posts with `action={dispatch}`, a nested submit button reads `useFormStatus` to disable itself, and `useOptimistic` shows the new name immediately and reverts automatically if the action fails, while I render the returned error. `use(promise)` reads a cached promise in render with Suspense. Caching, retries and complex validation still belong to a data or form library.
