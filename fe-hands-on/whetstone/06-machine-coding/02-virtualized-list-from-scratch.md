# Build a virtualized list from scratch (fixed and variable row heights)
**Round:** 06 · Machine Coding · **Level:** Lead / Staff · **Time:** 40 min · **Tags:** virtualization · windowing · performance
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
Render 100,000 rows smoothly by rendering only what's visible. Fixed heights first, then variable heights measured with ResizeObserver without scroll jumps, plus `scrollToIndex(i)`.

Tests: 100k × 40 px rows in a 400 px viewport → ~10 rows + overscan in DOM; `scrollTop = 40_000` → first visible index 1000; `scrollToIndex(5000)` puts row 5000 at top; a row growing 40 → 120 px shifts later rows without moving rows currently in view.

## Core answer (key points)
- **Structure:** scroll container (fixed height, `overflow:auto`) → spacer div with total height → absolutely positioned rows with `transform: translateY(offset)`.
- **Fixed math:** `start = floor(scrollTop / h) - overscan`, `end = ceil((scrollTop + viewport) / h) + overscan`, clamped. DOM nodes = O(visible), independent of N.
- **Variable heights:** keep `heights[]` (estimate until measured) and a prefix-sum `offsets[]`. Start index = binary search over offsets (O(log n)). Rebuild offsets lazily from the first dirty index.
- **Measurement:** one shared `ResizeObserver` watching rendered rows (`data-index`); on size change update heights and re-render.
- **Scroll anchoring:** if a row *above* the viewport changes height by Δ, adjust `scrollTop += Δ` so the content under the user's eyes stays put. (Browser CSS scroll anchoring doesn't help with absolute positioning.)
- **`scrollToIndex(i)`:** `container.scrollTop = offsetOf(i)`; for unmeasured targets, scroll, measure, correct once more.
- **Perf polish:** `contain: strict` on container, `will-change: transform` sparingly, rAF-throttle scroll state if rows are heavy, stable keys by item id.
- **A11y:** off-screen rows don't exist → expose `aria-rowcount`/`aria-rowindex` (grid) or `aria-setsize`/`aria-posinset` (list); keyboard nav index-based, scroll-then-focus.

## Mental model / flow
```
container (400px, overflow:auto, onScroll → scrollTop)
└─ spacer (height = total)
   ├─ row i   translateY(offset[i])
   ├─ row i+1 translateY(offset[i+1])
   └─ ...only start..end
offsets: [0, h0, h0+h1, ...]  start = upperBound(offsets, scrollTop) - 1
```

## Code sketch
```ts
// Prefix-sum index, lazily rebuilt — original outline
export class RowMetrics {
  private h: Float64Array;
  private off: Float64Array;
  private dirty = 0;
  constructor(n: number, est: number) {
    this.h = new Float64Array(n).fill(est);
    this.off = new Float64Array(n + 1);
  }
  set(i: number, px: number) {
    if (this.h[i] === px) return 0;
    const delta = px - this.h[i];
    this.h[i] = px;
    this.dirty = Math.min(this.dirty, i);
    return delta;
  }
  private build() {
    for (let i = this.dirty; i < this.h.length; i++) this.off[i + 1] = this.off[i] + this.h[i];
    this.dirty = this.h.length;
  }
  top(i: number) { this.build(); return this.off[i]; }
  total() { this.build(); return this.off[this.h.length]; }
  indexAt(y: number) {
    this.build();
    let lo = 0, hi = this.h.length - 1;
    while (lo < hi) { const mid = (lo + hi) >>> 1; this.off[mid + 1] <= y ? (lo = mid + 1) : (hi = mid); }
    return lo;
  }
}
```
```tsx
function VirtualList<T>({ items, estimate, height, overscan = 4, row, keyOf }: Props<T>) {
  const box = useRef<HTMLDivElement>(null);
  const metrics = useMemo(() => new RowMetrics(items.length, estimate), [items.length, estimate]);
  const [scrollTop, setScrollTop] = useState(0);
  const [, bump] = useReducer((n: number) => n + 1, 0);

  const ro = useMemo(() => new ResizeObserver(entries => {
    let changed = false;
    for (const e of entries) {
      const i = Number((e.target as HTMLElement).dataset.index);
      const d = metrics.set(i, e.borderBoxSize[0].blockSize);
      if (d && metrics.top(i) < box.current!.scrollTop) box.current!.scrollTop += d; // anchor
      changed ||= d !== 0;
    }
    if (changed) bump();
  }), [metrics]);
  useEffect(() => () => ro.disconnect(), [ro]);

  const first = Math.max(0, metrics.indexAt(scrollTop) - overscan);
  const last = Math.min(items.length - 1, metrics.indexAt(scrollTop + height) + overscan);

  return (
    <div ref={box} role="list" style={{ height, overflowY: 'auto', position: 'relative', contain: 'strict' }}
         onScroll={e => setScrollTop(e.currentTarget.scrollTop)}>
      <div style={{ height: metrics.total(), position: 'relative' }}>
        {range(first, last).map(i => (
          <div key={keyOf(items[i])} data-index={i} role="listitem"
               aria-setsize={items.length} aria-posinset={i + 1}
               ref={el => { if (el) { ro.observe(el); return () => ro.unobserve(el); } }}
               style={{ position: 'absolute', insetInline: 0, transform: `translateY(${metrics.top(i)}px)` }}>
            {row(items[i], i)}
          </div>
        ))}
      </div>
    </div>
  );
}
```
(Ref-callback cleanup requires React 19. `borderBoxSize` support is broad in modern browsers; fall back to `contentRect` if needed.)

## Trade-offs & pitfalls
- Fast flinging shows blank gaps if row render can't keep up: more overscan, lighter rows, placeholders.
- Ctrl+F can't find unrendered rows; for document-like content prefer CSS `content-visibility: auto`.
- Prepending items (chat) requires anchoring by key, not index.
- Mutating `RowMetrics` outside React state is deliberate (perf) but impure; keep it encapsulated and force renders explicitly.
- Production: TanStack Virtual, react-window, react-virtuoso handle grids, sticky headers, horizontal, quirks.

## Likely follow-ups
- **Why transform vs top?** Transform is compositor-friendly and avoids layout per row move.
- **Grid virtualization?** Two independent ranges (rows × columns) and a 2D spacer.
- **Sticky group headers?** Render the current group header outside the windowed set, positioned sticky.
- **Test it?** jsdom has no layout: mock `clientHeight`/`scrollTop`, stub ResizeObserver; assert rendered `data-index` range. Real perf in Playwright with a trace.

## Say it in 60 seconds
I render a fixed-height scroll container with a spacer as tall as the full list, and only the rows that intersect the viewport plus a few overscan rows, positioned with `translateY`. With fixed heights the visible range is simple division. For variable heights I keep a heights array with estimates, a lazily rebuilt prefix-sum of offsets, and binary-search the first visible row. A shared ResizeObserver measures rendered rows and updates heights; if a row above the viewport changes, I adjust `scrollTop` by the delta so nothing jumps. `scrollToIndex` is just setting `scrollTop` to that row's offset. For accessibility I expose set size and position since off-screen rows don't exist, and in production I'd use TanStack Virtual.
