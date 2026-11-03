# The critical rendering path: parse, style, layout, paint, composite. What triggers what?
**Round:** 07 · Browser & Web Platform · **Level:** Senior · **Time:** 15 min · **Tags:** rendering · layout · paint
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: a landing page is blank for ~2s on slow 4G, then everything pops in at once. Explain what the browser is doing and what you'd change.

## What they're really testing
Whether you can map "blank then pop" to specific blocking resources, and whether you know which style changes cost layout vs paint vs composite.

## Core answer (key points)
- **Pipeline:** bytes → HTML tokenizer → DOM; CSS → CSSOM; DOM + CSSOM → render tree (visible nodes + computed style) → layout (geometry) → paint (record draw ops per layer) → composite (GPU stitches layers into a frame).
- **"Blank then pop" = render-blocking.** The browser refuses to paint until all blocking CSS in `<head>` is parsed (to avoid FOUC). A big CSS file or a slow third-party stylesheet delays first paint for the whole page.
- **Parser-blocking JS.** A classic `<script>` without attributes halts HTML parsing while it downloads + executes (it might `document.write` or read styles, so it also waits for pending CSS).
  - `defer`: download in parallel, execute after parsing, in document order.
  - `async`: download in parallel, execute as soon as ready, any order; can still interrupt parsing.
  - `type="module"`: deferred by default; `async` is allowed on modules too.
- **Fonts:** with the default `font-display` behavior text can be invisible for a block period. Use `font-display: swap`/`optional` and preload the critical font.
- **Preload scanner:** a secondary parser that looks ahead in raw HTML for `src`/`href` and starts fetches early. Anything only discoverable after JS runs (CSS-in-JS injected styles, client-rendered `<img>`, background images in JS-built DOM) misses it and loads late.
- **Cost of a style change:**
  - Geometry (`width`, `height`, `top`, `left`, `font-size`, `padding`) → layout + paint + composite.
  - Visual only (`color`, `background-color`, `box-shadow`) → paint + composite.
  - `transform`, `opacity` on an element that has its own compositor layer → composite only, can run on the compositor thread.
- **Forced synchronous layout:** reading geometry (`offsetHeight`, `getBoundingClientRect`, `scrollTop`) after a write makes the browser flush layout now. In a loop it becomes **layout thrashing**.
- **Containment:** `contain: layout paint` / `contain: content` scopes invalidation to a subtree; `content-visibility: auto` skips rendering off-screen subtrees entirely (give it `contain-intrinsic-size` so the scrollbar doesn't jump).

## Mental model / flow
```
HTML ──parse──► DOM ─┐
                      ├─► Render tree ─► Style ─► Layout ─► Paint ─► Composite ─► pixels
CSS  ──parse──► CSSOM┘                  ▲          ▲         ▲          ▲
                                         │          │         │          │
              class/selector change ─────┘   width/top ─┘  color ─┘  transform/opacity ─┘
```
Blocking at load:
```
<link rel=stylesheet>  → blocks RENDER (no paint until CSSOM ready)
<script>               → blocks PARSER (and waits on earlier CSS)
<script defer|module>  → runs after parse, ordered
<script async>         → runs when downloaded, unordered
```

## Code sketch
```ts
// Thrash: each iteration reads after the previous write → forced layout per item.
rows.forEach((row) => {
  row.style.width = `${row.offsetWidth * 1.1}px`;
});

// Fix: read phase, then write phase (one layout).
const widths = rows.map((row) => row.offsetWidth);
rows.forEach((row, i) => {
  row.style.width = `${widths[i] * 1.1}px`;
});
```
```css
/* layout every frame */
.drawer { transition: left 200ms; }
/* compositor-only */
.drawer { transition: transform 200ms; }
.drawer.is-animating { will-change: transform; } /* add during animation, remove after */
```

## Trade-offs & pitfalls
- `will-change` everywhere = many layers = GPU memory pressure, worse on low-end phones. Scope it to the animation window.
- Inlining critical CSS speeds first paint but bloats every HTML response and defeats CSS caching; keep it small (above-the-fold only).
- `async` analytics can still block parsing when it lands mid-parse; for non-critical third parties prefer `defer` or load after `load`.
- In React, the common thrash source is many `useLayoutEffect`s each measuring then setting state. Batch measurement in one place, or use `ResizeObserver`.
- `content-visibility: auto` can break in-page find and anchor scroll offsets in some cases if intrinsic size is wrong; verify.

## Likely follow-ups
- **Why is `transform` cheaper than `top`?** `top` invalidates geometry (possibly siblings); `transform` only changes how an already-painted layer is placed, which the compositor does off the main thread.
- **What runs on the main thread during scroll?** Ideally nothing; the compositor scrolls. Non-passive `wheel`/`touchmove` listeners force it to wait on JS, so mark them `{ passive: true }`.
- **How do you verify?** DevTools Performance: purple = style/layout, green = paint, "Forced reflow" warnings with stack; Rendering tab → Paint flashing, Layer borders; Layers panel.
- **What would you change for the 2s blank?** Inline critical CSS, `defer` all scripts, preload the hero font/image, move render-critical resources out of JS so the preload scanner sees them, consider SSR so HTML carries content.
- **Does `async` on a module change anything?** Yes, it runs as soon as it and its imports load, no longer waiting for parse completion.

## Say it in 60 seconds
The browser parses HTML into the DOM and CSS into the CSSOM, combines them into a render tree, then runs style, layout, paint and composite. CSS blocks rendering and classic scripts block parsing, so a blank screen followed by everything at once usually means a large blocking stylesheet or synchronous scripts in the head. I'd inline critical CSS, defer scripts or make them modules, preload the late-discovered font and hero image, and make sure key resources are in the HTML so the preload scanner finds them. At runtime, geometry changes cost layout plus paint, colour changes cost paint, and transform/opacity can be composite-only, so I animate those. I also avoid read-write interleaving that forces synchronous layout, and use `contain` or `content-visibility` to limit work. Then I check the Performance panel for long purple and green blocks and forced-reflow warnings.
