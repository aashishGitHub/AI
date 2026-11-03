# Bundle strategy: code-splitting boundaries, vendor chunks, tree-shaking failures and budgets
**Round:** 08 · Performance · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** bundling · code splitting · tree shaking
Source: https://whetstone-v1.vercel.app/#performance

Scenario: main bundle is 1.4 MB gzip and growing. Design the strategy for a large React app: where to split, how to share vendor code, how to stop regressions. (Site offers React/Angular/Vue code; notes use React.)

## What they're really testing
Splitting judgment (route vs interaction), chunking that caches well, diagnosing where bytes come from, and the org mechanism that keeps the number down.

## Core answer (key points)
- **Split by route first**, so each page loads only its code. Then **by interaction**: heavy features loaded on demand (rich text editor, charts, PDF export, maps).
- **Prefetch on intent** (hover/focus/viewport, or router-level prefetch) so splitting doesn't make navigation slower.
- **Chunking:** a stable framework chunk (react, react-dom, router) that rarely changes and stays cached across deploys; a shared app-core chunk; route chunks. Avoid both one giant vendor chunk (busts on every dep bump) and hundreds of tiny chunks (overhead, worse compression). With HTTP/2/3, a few dozen requests is fine.
- **Diagnose:** bundle visualizer (rollup-plugin-visualizer, webpack-bundle-analyzer, source-map-explorer), look for duplicates and surprise heavyweights.
- **Tree-shaking failures:**
  - CommonJS dependencies (no static `import`/`export` to analyze).
  - Missing or wrong `"sideEffects"` in package.json, so the bundler keeps everything.
  - Barrel files (`index.ts` re-exporting everything) with side effects or that defeat per-module chunking.
  - Whole-library imports (`lodash`, full icon sets, `moment` + all locales).
- **Other bytes:** duplicate versions (dedupe, align ranges), legacy polyfills (target modern browsers), server-only libs in client (markdown, syntax highlight → do at build/server).
- **Stop regressions:** per-entry size budgets in CI (size-limit, bundlewatch, Lighthouse CI budgets) that comment deltas on PRs and fail on breach; route owners own budgets.

## Mental model / flow
```
framework chunk (react, router)  ── long-lived cache, changes rarely
app-core chunk (design system, api client, store)
route chunks: /home  /search  /reports  /settings
interaction chunks: chart-editor, pdf-export, rich-text  ← import() on click, warmed on hover
```
| Where bytes hide | Fix |
|---|---|
| `import _ from 'lodash'` | `lodash-es` per-function or native |
| moment + locales | date-fns / `Intl` / Temporal, load locale on demand |
| full icon pack | per-icon imports, SVG sprite |
| two versions of a dep | dedupe / resolutions |
| core-js for everything | modern targets |
| markdown/highlighting in client | render at build or server |

## Code sketch
```tsx
const Reports = lazy(() => import('./routes/Reports'));
const loadEditor = () => import('./features/chart-editor/ChartEditor');
const ChartEditor = lazy(loadEditor);

function EditChartButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onPointerEnter={() => void loadEditor()} onFocus={() => void loadEditor()} onClick={() => setOpen(true)}>
        Edit chart
      </button>
      {open && (
        <Suspense fallback={<EditorSkeleton />}>
          <ChartEditor />
        </Suspense>
      )}
    </>
  );
}
```
```json
// .size-limit.json
[
  { "path": "dist/assets/index-*.js", "limit": "130 kB", "gzip": true },
  { "path": "dist/assets/framework-*.js", "limit": "60 kB", "gzip": true }
]
```

## Trade-offs & pitfalls
- Over-splitting creates waterfalls (route chunk → its lazy child → its data). Hoist imports for things always needed together; preload in parallel with data.
- Lazy boundaries need Suspense fallbacks that don't cause CLS, and error boundaries for ChunkLoadError after deploys (see 07-02).
- `manualChunks`/`splitChunks` rules that are too clever break caching when a shared module moves.
- Gzip vs brotli vs parse cost: bytes over the wire aren't the whole story; JS parse/compile/execute on mid-range phones is the real cost.
- Barrel files also slow dev servers and tests; consider lint rules banning deep re-export barrels in app code.

## Likely follow-ups
- **How do you find who added 200 KB?** PR size comment with per-package attribution; `git bisect` against size-limit if it slipped through.
- **What does `sideEffects: false` actually promise?** That importing a module without using its exports can be dropped; wrong if the module registers globals or CSS.
- **Module federation / micro-frontends?** Share framework as singletons or you ship React N times; version skew is the main risk.
- **How does RSC/SSR change this?** Server components ship zero client JS for non-interactive parts, shrinking client bundles structurally.
- **Principal angle:** bundle size is a commons. Per-route budget dashboards, ownership, and explicit exceptions with a payback plan.

## Say it in 60 seconds
I split by route first so each page ships only its code, then by interaction so heavy features like editors, charts or PDF export load on demand, and I warm those chunks on hover or focus so users don't feel the split. For caching I keep a stable framework chunk, a shared core chunk and route chunks, avoiding both one giant vendor bundle and hundreds of tiny ones. To find the 1.4 MB I run a visualizer and look for the usual culprits: CommonJS deps that can't tree-shake, barrels and missing sideEffects flags, whole-library imports, duplicate versions, legacy polyfills and server-only libs in the client. Then I stop the creep with per-entry size budgets in CI that comment the delta on each PR and fail on breach, with route teams owning their budgets.
