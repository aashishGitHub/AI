# Where do you place error boundaries and Suspense boundaries in a large app?
**Round:** 05 · Component API Design · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** error boundaries · suspense · resilience
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
Resilience architecture: one widget throwing crashes the whole app, and every navigation shows a wall of spinners. Where do boundaries go, how do you recover and report, and what don't they catch?

## Core answer (key points)
- **Boundaries follow independent units of UI**, in three layers:
  1. **App shell** — last-resort fatal screen; should almost never fire.
  2. **Route** — a broken page keeps nav/header alive; reset on pathname change (`resetKeys`).
  3. **Widget/panel** — one failing chart doesn't blank the dashboard; inline "Couldn't load X · Retry".
- **Each error boundary = fallback + recovery + reporting.** `onError` → monitoring (Sentry etc.) with context tags; Retry calls `resetErrorBoundary` and resets the data layer's error state (e.g., TanStack Query's `useQueryErrorResetBoundary`).
- **Not caught:** event handlers, async code after render (timeouts, promises), the boundary itself, some SSR paths. Handle locally or push the error into state and rethrow in render.
- **React 19 root hooks:** `createRoot(el, { onCaughtError, onUncaughtError, onRecoverableError })` for central reporting.
- **Suspense placement** uses the same regions, chosen to control reveal order:
  - One per page → single skeleton, slowest widget gates all.
  - One per widget → streams in as ready, but popcorn and layout shift unless skeletons reserve real size.
  - Navigation in a **transition** so the old page stays until the new one is ready, instead of flashing fallback.
- **Avoid waterfalls:** start fetches at the route level (loaders/prefetch), not in nested child effects; Suspense doesn't fix sequential fetching.

## Mental model / flow
```
<AppBoundary>                 fatal only
  <Layout nav/header>
    <RouteBoundary resetKeys=[pathname]>
      <Suspense PageSkeleton>  (nav via startTransition → old page stays)
        <Dashboard>
          <Widget name=revenue>   = ErrorBoundary + Suspense(sized skeleton)
          <Widget name=incidents>
```

## Code sketch
```tsx
function Widget({ name, children }: { name: string; children: ReactNode }) {
  const { reset } = useQueryErrorResetBoundary();
  return (
    <ErrorBoundary
      onReset={reset}
      onError={(err, info) => monitor.capture(err, { tags: { widget: name }, extra: info })}
      fallbackRender={({ resetErrorBoundary }) => (
        <section aria-labelledby={`${name}-h`} className="widget widget--error">
          <h3 id={`${name}-h`}>{name}</h3>
          <p>Couldn't load this panel.</p>
          <button onClick={resetErrorBoundary}>Retry</button>
        </section>
      )}
    >
      <Suspense fallback={<WidgetSkeleton name={name} />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

function RouteBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <ErrorBoundary resetKeys={[pathname]} FallbackComponent={RouteError}>{children}</ErrorBoundary>;
}

// Event-handler errors: catch locally, or surface into render
function useThrowToBoundary() {
  const [, set] = useState();
  return (e: unknown) => set(() => { throw e; });
}
```
(`ErrorBoundary` here is from `react-error-boundary`; React itself still only exposes class-based boundaries, as far as I know.)

## Trade-offs & pitfalls
- Too fine-grained → fallback clutter and duplicated retry UX; too coarse → one failure blanks large areas.
- Retry without resetting the cache just re-throws the cached error.
- Skeletons that don't match final layout cause CLS; reserve height.
- Swallowing errors in a boundary without reporting = invisible outages. Alert on boundary fire rate.
- Suspense fallback flashing on fast loads: transitions, or a minimum delay before showing skeletons.

## Likely follow-ups
- **Error boundary vs try/catch?** Boundaries catch render/lifecycle errors in the subtree; try/catch is for imperative code.
- **How does Next.js map this?** `error.tsx` per route segment and `loading.tsx` as Suspense boundaries (App Router conventions; verify for your version).
- **Order of reveal?** Nest boundaries top-to-bottom; `SuspenseList` was experimental and I'm not certain of its current status.
- **What's a "recoverable error"?** E.g. hydration mismatch React recovered from by client-rendering; report via `onRecoverableError`.

## Say it in 60 seconds
I place boundaries along independent pieces of UI: one at the shell as a last resort, one per route that resets on navigation so a broken page never kills the nav, and one per self-contained widget so a failing chart shows an inline retry instead of blanking the dashboard. Every boundary reports to monitoring and its Retry also resets the data layer. Boundaries don't catch event handler or async errors, so those are handled locally or pushed into render. Suspense boundaries use the same regions; I choose them for a deliberate reveal order with skeletons sized like the content, and navigate inside a transition so the old page stays visible rather than a wall of spinners.
