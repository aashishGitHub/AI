# Design a real-time analytics dashboard (Datadog/Grafana-like): data flow, charts and backpressure
**Round:** 12 · Frontend System Design · **Level:** Lead / Staff · **Time:** 30 min · **Tags:** system design · dashboards · real-time
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: dozens of widgets, each with time range, auto-refresh and live updates; on wall screens for hours.

## What they're really testing
A central query layer (dedupe, batch, pause), backpressure between network rate and frame rate, downsampling to pixel width, canvas rendering, widget isolation, and bounded memory over long sessions.

## Core answer (key points)
- **Requirements:** widget types (timeseries, top-N, single stat, heatmap), 10-40 per board; time range presets + custom; auto-refresh; live tail; crosshair sync; drill-down; shareable state. Scale: thousands of points per widget, 1s updates in live mode. NFRs: UI never freezes, no leaks over hours.
- **Model:** dashboard = grid of independent widgets; each has a *query spec*, a time range (inherited or overridden) and a refresh policy.
- **URL is the source of truth** for dashboard id, `from`, `to`, `tz`, template vars. Relative ranges (`now-1h`) resolved at query time.
- **QueryScheduler:** hash each spec+range; dedupe identical specs across widgets; batch into one request; concurrency limit; per-query timeout/retry; pause on `visibilitychange` hidden; refetch range on return.
- **Live mode:** WebSocket (or SSE) per dashboard multiplexing series subscriptions. Incoming points go to a per-series **ring buffer** (bounded memory), not straight to state.
- **Backpressure:** coalesce: flush buffered points at most once per animation frame (or per second for wall screens). When hidden, rAF stops, so cap the buffer and drop oldest, or discard and refetch the range on return.
- **Downsampling:** a 600 px chart can't show 50k points. Prefer server-side (query by step = range/width). Client fallback in a worker: min/max per pixel bucket (keeps spikes) or LTTB (keeps visual shape).
- **Rendering:** SVG fine up to roughly hundreds of points; canvas for tens of thousands; WebGL beyond (rough figures, depends on device). Keep chart instances mounted and update data in place (uPlot/ECharts) rather than re-creating per tick.
- **Isolation:** per-widget loading/error/stale state, error boundary, "data as of 12:01:05" badge when stale. One slow query never blocks others.
- **Interaction:** crosshair sync via a tiny external store with per-chart subscription (not React context re-rendering 40 widgets per mousemove). Brush-to-zoom writes URL range → back button works.
- **A11y:** table alternative per chart, keyboard-reachable legend/tooltips, contrast and non-colour encodings (dash patterns, markers).
- **Time/clock:** display in chosen tz; server timestamps are UTC; guard against client clock skew when computing "now".

## Mental model / flow
```
URL (dashId, from, to, tz, vars)
        │ parse
        ▼
  DashboardStore ──► Widget[] (spec + range + refresh)
                          │ subscribe(spec)
                          ▼
                 ┌─────────────────── QueryScheduler ───────────────────┐
                 │ hash(spec,range) → dedupe · batch · limit N · timeout │
                 │ pause when hidden · refetch on visible                 │
                 └───────┬───────────────────────────────┬───────────────┘
            historical   │ POST /api/query (batched)     │ live: WebSocket (multiplexed)
                         ▼                               ▼
                 ResultCache(hash)              RingBuffer per series (capped)
                         │                               │ FrameCoalescer (≤1 flush / rAF)
                         └──────────────┬────────────────┘
                                        ▼
                     Downsampler (server step, or Worker: min/max | LTTB → width px)
                                        ▼
                     Chart instance (canvas/WebGL, mounted, setData in place)
                                        ▲
             CrosshairStore (external, per-chart subscribe) ──┘
```

## Code sketch
```ts
class RingBuffer<T> {
  private buf: (T | undefined)[]; private head = 0; private size = 0;
  constructor(private cap: number) { this.buf = new Array(cap); }
  push(v: T) { this.buf[(this.head + this.size) % this.cap] = v; if (this.size < this.cap) this.size++; else this.head = (this.head + 1) % this.cap; }
  toArray(): T[] { return Array.from({ length: this.size }, (_, i) => this.buf[(this.head + i) % this.cap] as T); }
}

function coalescePerFrame<T>(onFlush: (batch: T[]) => void) {
  let pending: T[] = []; let scheduled = false;
  return (item: T) => {
    pending.push(item);
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; const b = pending; pending = []; onFlush(b); });
  };
}

function minMaxPerPixel(xs: number[], ys: number[], width: number) {
  const out: [number, number][] = []; const step = Math.ceil(xs.length / width);
  for (let i = 0; i < xs.length; i += step) {
    let lo = i, hi = i;
    for (let j = i; j < Math.min(i + step, xs.length); j++) { if (ys[j] < ys[lo]) lo = j; if (ys[j] > ys[hi]) hi = j; }
    for (const k of lo < hi ? [lo, hi] : [hi, lo]) out.push([xs[k], ys[k]]);
  }
  return out;
}
```

## Trade-offs & pitfalls
- Polling vs push: polling is simpler, cache-friendly and fine at 10-30s; push for sub-second live tail. Many products do both (poll history, push tail).
- Pending array in the coalescer grows unbounded while hidden; combine with the ring buffer cap.
- Downsampling on the client still ships all points over the wire; push it to the query layer.
- Canvas charts are invisible to AT; provide data tables / summaries.
- Re-rendering the whole grid on any store change; subscribe per widget with selectors.
- Memory leaks: listeners/sockets not cleaned on widget unmount; chart instances not destroyed.

## Likely follow-ups
- *How do you test it for hours?* Soak test in Playwright with fake clock + synthetic stream; track heap snapshots and long animation frames.
- *Hundreds of viewers on one dashboard?* Server fans out same query result; client dedupe doesn't help cross-user, server cache does.
- *Template variables (`$host`)?* Part of URL and spec hash; change triggers refetch of dependent widgets only.
- *Why worker for downsampling?* Keeps main thread free for interaction (INP) when series are large.

## Say it in 60 seconds
A dashboard is a grid of independent widgets, each with a query spec, a time range and a refresh policy, and the URL holds the range and variables. All fetching goes through one query scheduler that hashes specs, dedupes identical ones, batches them, caps concurrency, and pauses when the tab is hidden. Live data arrives over one multiplexed WebSocket into a capped ring buffer per series. I flush at most once per animation frame, so network rate never dictates render rate. Points are downsampled to the chart's pixel width, ideally server-side, otherwise min/max or LTTB in a worker. I render on canvas with chart instances kept mounted. Each widget isolates its own loading, error and stale states, crosshair sync uses an external store with per-chart subscriptions, and charts get table alternatives for accessibility.
