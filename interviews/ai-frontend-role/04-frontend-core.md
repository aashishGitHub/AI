# 04 · Frontend core (the bar you still have to clear)

AI teams still run a normal senior FE loop. Short, answer-first versions here; each section links the deep notes in
[`fe-hands-on/whetstone/`](../../fe-hands-on/whetstone/README.md). React/Next details move fast: check react.dev and nextjs.org the week of the interview.

---

## A. JavaScript runtime — deep: [whetstone/01](../../fe-hands-on/whetstone/01-javascript-internals/README.md)

### Q1 🟡 Explain the event loop, including microtasks and rendering.
**A.** One main thread. Run one **task** (macrotask: script, timer callback, event handler, message) to completion → drain **all microtasks** (promise reactions, `queueMicrotask`, MutationObserver) → the browser *may* render (run `requestAnimationFrame` callbacks, style, layout, paint) → next task. Consequences: a long task blocks input and paint (bad INP); an infinite microtask chain starves rendering; `setTimeout(fn, 0)` runs after pending microtasks and possibly after a render; `await` resumes as a microtask.
For streaming UIs: token handlers run as tasks/microtasks; coalesce into one rAF flush per frame.

### Q2 🟡 How do closures cause memory leaks in SPAs?
**A.** A closure keeps its outer variables alive. Leaks happen when something long-lived holds the closure: an event listener on `window` not removed on unmount, a `setInterval` never cleared, a subscription to a global store, a cache Map keyed by objects. Fixes: cleanup in effects, `AbortController` signal to remove many listeners at once (`addEventListener(..., { signal })`), `WeakMap` for object-keyed caches. Find them with heap snapshots (DevTools Memory → compare snapshots, look at detached DOM nodes).

### Q3 🟢 `this` binding rules?
**A.** Determined by the call site: `new` → the new object; `call/apply/bind` → the given object; `obj.method()` → `obj`; plain call → `undefined` in strict mode (global in sloppy). Arrow functions have no own `this`; they capture it lexically. Class field arrow methods bind per instance (costs memory per instance, handy for callbacks).

### Q4 🟡 Promises vs async/await, and error-handling pitfalls?
**A.** `async/await` is syntax over promises. Pitfalls: sequential `await` in a loop when the calls are independent (use `Promise.all`); `Promise.all` rejects on first failure (use `Promise.allSettled` when you want all results); `forEach` with an async callback doesn't wait; un-awaited promise rejections go unhandled; `try/catch` only catches awaited rejections. `Promise.race` / `Promise.any` for timeouts and first-success.

### Q5 🟡 ESM vs CommonJS?
**A.** ESM: static `import/export`, analysed at build time → tree-shaking, top-level `await`, async loading, live bindings. CJS: `require` at runtime, synchronous, `module.exports` object copy. Interop pain: default-export mismatches, dual-package hazard (two copies of a library loaded). Libraries should ship ESM with a correct `exports` map.

### Q6 🟡 Generators and async iterators — any real use?
**A.** Yes, streaming. `for await (const chunk of stream)` reads a `ReadableStream` (async-iterable in modern browsers and Node; verify Safari support for your target) — and you can write an async generator that turns a byte stream into parsed SSE events, which composes cleanly: `for await (const evt of parseSSE(res.body)) dispatch(evt)`.

---

## B. TypeScript — deep: [whetstone/02](../../fe-hands-on/whetstone/02-typescript/README.md)

### Q7 🟡 How do you model UI state so impossible states can't be represented?
**A.** Discriminated unions instead of booleans:
```ts
type Req<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };
```
`switch (s.status)` narrows the type; add an exhaustive `default: const _x: never = s` so a new status breaks the build where it isn't handled. Same for stream events.

### Q8 🟡 `unknown` vs `any`, `satisfies`, type assertions?
**A.** `any` turns checking off; `unknown` forces narrowing before use — use it for network/model data, then validate (Zod `parse` gives you a typed value). `satisfies` checks a value matches a type **without widening** it (keeps literal types, e.g. a config object). `as` asserts without checking — avoid it on external data; it's how runtime bugs sneak past the compiler.

### Q9 🟡 Why do you need runtime validation if you have TypeScript?
**A.** Types are erased at runtime. API responses, `localStorage`, `postMessage`, URL params, and **LLM output** can be anything. Validate at the boundary with a schema (Zod/Valibot) and derive the TS type from the schema (`z.infer`) so there's one source of truth.

### Q10 🟡 Generics: give a real example.
**A.** A typed tool registry for generative UI:
```ts
const registry = {
  weather: { schema: WeatherProps, Component: WeatherCard },
  table:   { schema: TableProps,   Component: DataTable },
} satisfies Record<string, { schema: z.ZodTypeAny; Component: React.ComponentType<any> }>;
type ToolName = keyof typeof registry;
```
Rendering looks up by name, validates with the schema, then renders — unknown names and bad props are handled at one place.

---

## C. React — deep: [whetstone/04](../../fe-hands-on/whetstone/04-react-internals/README.md), [05](../../fe-hands-on/whetstone/05-component-api-design/README.md)

### Q11 🟡 What happens from `setState` to pixels?
**A.** `setState` schedules an update with a priority (lane) → React batches updates → **render phase**: calls components, builds the new tree, diffs against the old (reconciliation; interruptible in concurrent rendering) → **commit phase** (synchronous): applies DOM mutations, runs layout effects (`useLayoutEffect`), browser paints, then passive effects (`useEffect`) run. Renders must be pure because they can run more than once or be thrown away.

### Q12 🟡 Why does a component re-render, and how do you stop unnecessary ones?
**A.** It re-renders when its state changes, its parent re-renders, or a context it reads changes. Fixes, in order: move state down (colocate), lift content up (pass children so they don't re-render), split contexts (or use a store with selectors), `memo` + stable props (`useMemo`/`useCallback`) where profiling shows cost. With the **React Compiler** (auto-memoisation; v1.0 released in 2025 — verify current status) much manual memoisation becomes unnecessary, but it doesn't fix bad state placement or expensive renders.

### Q13 🟡 "Effects are for synchronisation" — what does that mean?
**A.** `useEffect` is for syncing with something **outside React** (network subscription, DOM API, timer, external store). Not for deriving state from props (compute during render), not for reacting to events (do it in the event handler), not for data fetching chains if a framework/query library can do it. Common bug: effect sets state that triggers the effect again. Every effect needs a cleanup if it subscribes. In dev Strict Mode, React mounts → unmounts → remounts to expose missing cleanups.

### Q14 🟡 Stale closures in hooks — example and fix?
**A.** An interval created in `useEffect(() => { setInterval(() => setCount(count + 1), 1000) }, [])` always sees `count = 0`. Fixes: functional update `setCount(c => c + 1)`, put the value in a ref, or add the dependency (and recreate the interval). React 19.2 added `useEffectEvent` for reading latest values inside effects without re-subscribing (verify it's stable in your React version).

### Q15 🟡 Transitions, `useDeferredValue`, Suspense — when?
**A.** `startTransition` / `useTransition`: mark an update non-urgent so typing stays responsive while a big list re-renders; React can interrupt it. `useDeferredValue`: render with an older value while the new one computes in the background (search-as-you-type over a big list). Suspense: declarative loading boundaries for code (`lazy`) and data (with a Suspense-enabled source or `use()`); with streaming SSR, each boundary streams its HTML when ready.

### Q16 🟡 React 19 features you should name?
**A.** **Actions** (async functions in transitions, form `action={fn}`), `useActionState` (pending + result of an action), `useFormStatus` (from `react-dom`, pending state inside a form), `useOptimistic`, `use()` (read a promise or context, can be called conditionally), `ref` as a regular prop (no `forwardRef` needed for function components), document metadata (`<title>` in components), Server Components + Server Actions (`'use server'`) in frameworks. 19.2: `<Activity>` (hide UI but keep its state) and `useEffectEvent`. Verify minor-version details on react.dev.

### Q17 🔴 Server Components: what are they, and when do they hurt?
**A.** Components that run only on the server (at request or build time), can read data directly, and send a serialized result (not their JS) to the client → less client JS. `'use client'` marks the boundary; everything imported below it is client code. **They hurt** when: the UI is highly interactive (everything becomes client anyway), you pass large serialised props across the boundary, you create waterfalls with nested sequential awaits, your team's mental model of what runs where is weak (security bugs: leaking server-only data into props), or your backend is a separate API anyway (RSC adds a hop). For an AI chat: the shell, history list, and settings can be RSC; the live chat panel is a client component.

### Q18 🟡 Hydration mismatch — causes and fixes?
**A.** Server HTML differs from the first client render: `Date.now()`/random values, `window`/`localStorage` reads during render, locale/timezone formatting, browser extensions altering DOM, invalid HTML nesting (`<div>` in `<p>`). Fixes: render the deterministic value on the server and update in an effect, `suppressHydrationWarning` for known one-element cases (timestamps), client-only components for browser-dependent UI, consistent locale/timezone.

### Q19 🟡 Controlled vs uncontrolled — and how do you design a component that supports both?
**A.** Controlled: parent owns the value via props + onChange. Uncontrolled: component owns internal state, parent reads via ref or events. A `useControllableState({ value, defaultValue, onChange })` hook supports both: if `value !== undefined` use it, else internal state; always call `onChange`. That's how headless UI libraries do it.

### Q20 🟡 Compound components and headless components?
**A.** Compound: `<Tabs><Tabs.List><Tabs.Tab/></Tabs.List><Tabs.Panel/></Tabs>` sharing state via context — flexible markup, clear API. Headless: logic + a11y in hooks (`useCombobox`) with zero styling, consumers own the markup. Design systems at scale use headless primitives (Radix, React Aria — know the names) + their own styled layer.

### Q21 🟡 Error boundaries — what do they catch and not catch?
**A.** They catch errors thrown during render, lifecycle, and constructors of their children, and show a fallback. They don't catch errors in event handlers, async code (promises, timers), SSR, or in the boundary itself — handle those with try/catch and report. Put boundaries around independent widgets (the AI panel!) so one failure doesn't blank the page; reset on route change or retry.

---

## D. Next.js / rendering strategy — deep: [whetstone/13-04](../../fe-hands-on/whetstone/13-architecture-at-scale/04-choose-rendering-architecture-per-surface.md)

### Q22 🟡 CSR vs SSR vs SSG vs ISR vs streaming SSR — pick per surface.
**A.**
| Strategy | When | Cost |
|---|---|---|
| CSR | Authenticated dashboards, heavy interactivity | Slow first paint, SEO weak |
| SSR | Personalised pages needing fast first paint | Server cost per request, TTFB |
| SSG | Marketing, docs | Rebuild to update |
| ISR / revalidation | Mostly static, periodically updated | Staleness window |
| Streaming SSR + Suspense | Pages with slow parts | Complexity; boundaries must be designed |
Per-surface, not per-app: docs = SSG, console = SSR shell + client islands, AI chat = SSR shell + client streaming panel.

### Q23 🟡 What changed in recent Next.js versions that interviewers ask about?
**A.** App Router + RSC by default; Next 15 changed defaults so `fetch` and GET route handlers are **not cached by default** (opt-in caching); async request APIs (`cookies()`, `headers()`, `params` are async); Server Actions; Partial Prerendering (static shell + dynamic holes); Next 16 (late 2025) made Turbopack the default bundler and introduced Cache Components / the `'use cache'` directive. **I'm not certain of every detail here — verify on nextjs.org before the interview.**

---

## E. Performance — deep: [whetstone/08](../../fe-hands-on/whetstone/08-performance/README.md). Your story: **LCP 22s+ → 6–7s**.

### Q24 🟢 Core Web Vitals and thresholds?
**A.** Measured at the **75th percentile** of real users. **LCP** (Largest Contentful Paint, loading) good ≤ 2.5 s · **INP** (Interaction to Next Paint, responsiveness; replaced FID in March 2024) good ≤ 200 ms · **CLS** (Cumulative Layout Shift, visual stability) good ≤ 0.1.

### Q25 🟡 LCP is bad. How do you diagnose it?
**A.** Break LCP into sub-parts: **TTFB** → **resource load delay** (time until the LCP resource starts loading) → **resource load duration** → **element render delay**. Find the LCP element (DevTools Performance panel / web-vitals attribution), then fix the biggest sub-part: slow server/no CDN (TTFB); LCP image discovered late (`<link rel="preload">`, `fetchpriority="high"`, don't lazy-load it, don't render it from client JS); big image (responsive `srcset`, AVIF/WebP); render-blocking CSS/JS, or a client-side data waterfall before anything renders (SSR the shell, parallelise requests).
Tell your story at this level: which sub-part dominated on the Capella console and what you changed. Say honestly that sub-3 s is not done yet if it isn't.

### Q26 🟡 INP is bad. How do you fix it?
**A.** INP = input delay + processing time + presentation delay of the slowest interactions. Find long tasks during interactions (Performance panel, Long Animation Frames API in RUM). Fixes: break up long tasks and **yield** to the main thread (`scheduler.yield()` where supported, else `setTimeout`/`MessageChannel`), `startTransition` for non-urgent renders, virtualise big lists, debounce expensive handlers, move heavy work (parsing, diffing, syntax highlighting) to a Web Worker, avoid layout thrashing (read then write, not interleaved), reduce DOM size.

### Q27 🟡 CLS fixes?
**A.** Width/height or `aspect-ratio` on images and embeds; reserve space for ads, banners, async content; don't insert content above existing content unless user-initiated; fonts: `font-display` + size-adjusted fallbacks to cut swap shift; animate `transform`, not layout properties.

### Q28 🟡 Bundle strategy?
**A.** Route-level code splitting, lazy-load heavy widgets (charts, editors, Markdown + highlighter for AI chat), check bundle composition (analyser), drop or replace heavy deps, tree-shakable ESM imports, a performance budget enforced in CI (bundle size + Lighthouse CI on key routes), modern-browser targets only. Prefetch the next likely route on hover/idle.

### Q29 🟡 Lab vs field data?
**A.** Lab (Lighthouse, WebPageTest): controlled, reproducible, good for debugging and CI. Field / RUM (CrUX, `web-vitals` library sending to your analytics): real devices and networks, what users feel, what Google uses. Lab can look fine while field p75 is bad (slow devices, long sessions, interactions lab doesn't do — INP especially needs field data).

---

## F. Browser platform — deep: [whetstone/07](../../fe-hands-on/whetstone/07-browser-platform/README.md)

### Q30 🟡 HTTP caching for a SPA?
**A.** Hashed static assets (`app.3f9a.js`): `Cache-Control: public, max-age=31536000, immutable`. `index.html`: `no-cache` (revalidate every time, with ETag) so deploys take effect. API: usually `private, no-store` or short max-age + `stale-while-revalidate` where safe. Never long-cache unhashed files.

### Q31 🟡 CORS in one breath?
**A.** Browser-enforced: a page on origin A can't read responses from origin B unless B's response has `Access-Control-Allow-Origin` matching A. Non-simple requests (JSON content-type, custom headers like `Authorization`, methods beyond GET/POST/HEAD) send an `OPTIONS` **preflight** first. Credentials (cookies) need `Access-Control-Allow-Credentials: true` and an explicit origin, not `*`. CORS protects users' data from other sites; it is not server-side auth. My Go server has an `ALLOWED_ORIGINS` allowlist.

### Q32 🟡 Client storage: which one when?
**A.** Cookies (small, sent with every request; httpOnly for session tokens) · `localStorage` (sync, ~MBs, strings, same-origin, blocks main thread — small prefs only) · `sessionStorage` (per tab) · **IndexedDB** (async, large, structured — drafts, offline caches, chat history) · Cache Storage (Service Worker responses). Cross-tab: `BroadcastChannel` or `storage` events.

### Q33 🟡 Web Workers vs Service Workers?
**A.** Web Worker: background thread for CPU work (parsing, diffing, search indexing), talks via `postMessage`, no DOM. Service Worker: a network proxy for the origin — offline caching, background sync, push; lifecycle (install/activate/update) is the source of most bugs (stale versions; needs an update strategy and "new version available" prompt).

---

## G. Accessibility — deep: [whetstone/10](../../fe-hands-on/whetstone/10-accessibility/README.md)

### Q34 🟢 First rule of ARIA?
**A.** Don't use ARIA if a native HTML element does the job (`<button>`, not `<div role="button">`). ARIA changes what assistive tech announces, not behaviour — you'd have to add keyboard handling, focus, and states yourself. No ARIA is better than wrong ARIA.

### Q35 🟡 Focus management in a SPA?
**A.** On route change, move focus to the main heading (or a skip target) and announce the new page; in modals, trap focus, `Esc` closes, return focus to the trigger on close (native `<dialog>` with `showModal()` handles a lot of this); after deleting an item, move focus somewhere sensible, not to `<body>`. Visible focus styles (`:focus-visible`).

### Q36 🟡 Live regions?
**A.** `aria-live="polite"` (announce when idle) or `"assertive"` (interrupt; rarely), or roles `status` (polite) / `alert` (assertive) / `log`. The region must exist in the DOM before content changes. For AI streaming, announce start and completion, not every token.

### Q37 🟡 Accessible combobox/autocomplete essentials?
**A.** Input with `role="combobox"`, `aria-expanded`, `aria-controls` → `listbox`, options `role="option"` with `aria-selected`, `aria-activedescendant` on the input pointing to the highlighted option (focus stays in the input), arrow keys / Enter / Esc, announce result count via a live region. Follow the WAI-ARIA Authoring Practices combobox pattern.

---

## H. Security — deep: [whetstone/11](../../fe-hands-on/whetstone/11-security/README.md)

### Q38 🟡 XSS in React apps — where does it still happen?
**A.** React escapes text by default. Holes: `dangerouslySetInnerHTML` (model output!), `href={userUrl}` with `javascript:` URLs, rendering user HTML from a CMS, SSR injecting unescaped JSON into a `<script>` tag, third-party scripts. Defences: sanitise (DOMPurify) when HTML is unavoidable, URL scheme allowlist, strict CSP with nonces, Trusted Types to make DOM sinks enforce sanitisation.

### Q39 🟡 Where should a SPA keep auth tokens?
**A.** Best practice: no tokens in JS at all — a **BFF** holds tokens server-side and the browser gets an `httpOnly; Secure; SameSite` session cookie. `localStorage` tokens are stealable by any XSS. In-memory access token + refresh via httpOnly cookie is the middle ground. OAuth in the browser = Authorization Code + **PKCE** (Proof Key for Code Exchange), never the implicit flow.

### Q40 🟡 CSRF — still a thing?
**A.** Less so with `SameSite=Lax` default cookies in modern browsers, but still: use `SameSite=Lax/Strict`, CSRF tokens or double-submit for cookie-authenticated state-changing requests, check `Origin` header, never change state on GET. Server Actions frameworks typically add origin checks — verify for your framework version.

### Q41 🟡 Front-end supply-chain security?
**A.** Lockfiles committed, `npm ci` in CI, dependency review/audit and automated updates (Renovate/Dependabot), minimal dependencies, pin and SRI (Subresource Integrity) for third-party CDN scripts, CSP limiting script sources, watch for install scripts, npm provenance where available. The 2025 npm worm/compromised-maintainer incidents are a good "why this matters" example (verify details before quoting).

---

## I. Testing — deep: [whetstone/09](../../fe-hands-on/whetstone/09-testing-quality/README.md)

### Q42 🟡 Your frontend testing strategy for a large product?
**A.** "Testing trophy": static (TS, ESLint) → lots of **integration/component tests** (Testing Library + MSW; test behaviour the user sees) → focused unit tests for pure logic (parsers, reducers, utils) → a thin set of **E2E** (Playwright) on critical journeys → visual regression for the design system → automated a11y (axe) in component and E2E tests. Flaky-test policy: quarantine + fix owner + deadline. Contract tests or typed clients for the API boundary.

### Q43 🟡 Why Testing Library queries by role?
**A.** `getByRole('button', { name: /send/i })` tests what users and assistive tech perceive, so tests survive refactors and double as accessibility checks. Prefer role → label → text; `data-testid` last.

### Q44 🟡 Why MSW over mocking `fetch`?
**A.** MSW intercepts at the network level, so your real data-fetching code (headers, parsing, retries, streaming) runs. Same handlers work in tests, Storybook, and local dev. Mocking `fetch` directly tests your mock.

### Q45 🟡 Testing timers and async hooks?
**A.** Fake timers (`vi.useFakeTimers()` / Jest equivalents) for debounce, retry backoff, countdowns; advance time explicitly; `await` the resulting promises (`findBy*` / `waitFor`). For hooks, `renderHook`. Always restore real timers.

---

## J. Architecture at scale — deep: [whetstone/13](../../fe-hands-on/whetstone/13-architecture-at-scale/README.md)

### Q46 🔴 Micro-frontends: when yes, when no?
**A.** Yes: many teams that must deploy independently, clear domain boundaries, a legacy app to migrate piece by piece (strangler fig). No: one or two teams, shared heavy state across features, perf-critical pages. Costs: duplicated deps (bundle), version skew, inconsistent UX, cross-app routing/state, harder local dev. Prefer a modular monorepo with enforced boundaries first; Module Federation or route-level split apps when org structure demands it.

### Q47 🟡 Monorepo tooling and boundaries?
**A.** One repo, many packages (apps, design system, shared utils), task runner with caching (Nx/Turborepo), affected-only CI, enforced import boundaries (lint rules / project tags), codeowners, shared TS config. Benefit: atomic cross-package changes. Cost: CI scale, tooling ownership.

### Q48 🟡 How do you choose state management?
**A.** By kind of state: **server state** → TanStack Query/SWR/RSC (caching, dedupe, invalidation); **URL state** → the router (filters, tabs, IDs: shareable, back button works); **form state** → React Hook Form + Zod; **local UI state** → `useState`/`useReducer`; **global client state** (rare: auth user, theme, a live stream) → context for low-frequency, a small store (Zustand/Redux Toolkit) with selectors for high-frequency. Most "we need Redux" apps actually have server state.

### Q49 🟡 Design system as a product?
**A.** Tokens (colour, spacing, type) → headless accessible primitives → styled components → patterns/templates; versioned and documented (Storybook), with visual + a11y tests, a contribution model, adoption metrics, deprecation policy, and codemods for breaking changes. For AI: add patterns for chat messages, streaming states, citations, tool-approval cards, feedback controls — so every team's AI feature behaves consistently.

### Q50 🟡 Frontend observability?
**A.** RUM for Web Vitals by route/release, error tracking with source maps and release tags, session context (not full replay of sensitive screens), custom spans for key interactions (send → first token → done), trace ID propagated to the backend, alerts on p75 regressions and error-rate spikes per release, feature-flag-aware dashboards.
