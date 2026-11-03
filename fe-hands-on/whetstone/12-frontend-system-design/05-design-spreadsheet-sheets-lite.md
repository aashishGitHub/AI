# Design a spreadsheet (Google Sheets lite): grid virtualization, formulas and collaboration
**Round:** 12 · Frontend System Design · **Level:** Principal · **Time:** 35 min · **Tags:** system design · spreadsheet · virtualization
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: browser spreadsheet supporting very large sheets, formulas with dependencies, copy/paste and shared editing. (The prompt says 1M rows; the site's requirements list says 100k × 1k columns, mostly empty. Clarify the target in the interview.)

## What they're really testing
Sparse data modelling, 2D virtualization and DOM-vs-canvas, a formula engine with a dependency graph and topological recalculation, off-main-thread compute, and collaborative operations that rewrite references.

## Core answer (key points)
- **Requirements:** select, edit, copy/paste, fill handle, resize, freeze panes; formulas with refs/ranges/cross-sheet; errors `#REF!`, `#DIV/0!`, cycle error; multi-user editing; per-user undo.
- **Data model:** sparse `Map<cellKey, Cell>` (most cells empty). `Cell = { raw, value, ast?, format? }`. Row heights / col widths store only overrides. Use numeric `(row, col)` keys internally for speed; A1 notation only at the edges.
- **Dependency graph:** `precedents` (what I read) and `dependents` (who reads me). Ranges stored as ranges with an interval index, not 10k edges.
- **Recalc:** on edit → parse once to AST → update edges → collect transitive dependents → topological order → evaluate each once. DFS with an "in progress" set detects cycles; mark the cycle cells with an error. Volatile functions (`NOW`, `RAND`) recompute on every change/tick.
- **Off main thread:** for big sheets, run parse/recalc in a Web Worker holding the model; post back changed values in batches. UI stays responsive.
- **Rendering:** 2D virtualization: compute visible row/col window via prefix sums of sizes (binary search on scroll offset). DOM works for modest grids; canvas (Sheets-style) for huge ones, plus a positioned `<textarea>` overlay for editing and a small hidden `role="grid"` DOM mirror of the visible window for screen readers (`aria-activedescendant` or roving focus, live-region announcement of the focused cell).
- **Frozen panes:** separate panes sharing scroll positions on one axis.
- **Collaboration:** ops like `setCell(r,c,raw)`, `insertRows(at,n)`, `deleteCols(at,n)`. Server assigns total order; clients apply optimistically and rebase. Structural ops must transform references inside formulas (OT-style): inserting a row above `A5` rewrites `=A5` to `=A6`; deleting a referenced cell yields `#REF!`.
- **Presence:** selections broadcast over WebSocket, drawn as coloured borders.
- **Undo:** per-user stack of inverse ops, transformed against later remote ops.
- **Clipboard:** copy TSV + HTML table (Excel/Sheets interop); paste parses both; a big paste = one batched op and one undo step.
- **Perf targets (my suggestion):** scroll at 60fps, edit-to-visible-recalc under ~100ms for typical sheets.

## Mental model / flow
```
                    ┌───────────────────────── Main thread ─────────────────────────┐
 keyboard/mouse ──► │ SelectionModel ─► Editor overlay (<textarea>) ─► commit(raw)  │
                    │        │                                          │           │
 scroll ──────────► │ Viewport (prefix sums → visible rows/cols)        │ op        │
                    │        │                                          ▼           │
                    │ CanvasRenderer ◄── visible values ── ValueCache  OpQueue ─────┼──► WebSocket ──► Sync server
                    │ a11y grid mirror (visible window, aria)  ▲        │ optimistic │     (total order, transform
                    └──────────────────────────────────────────┼────────┼────────────┘      refs on structural ops)
                                                               │        ▼                         │
                    ┌──────────────────── Worker ──────────────┴────────────────┐                 │
                    │ Sparse model ─► parse AST ─► update dep graph ─► topo sort │ ◄── remote ops ─┘
                    │ ─► evaluate dependents once ─► cycle check ─► diff values  │
                    └────────────────────────────────────────────────────────────┘
```

## Code sketch
```ts
type Key = number; // row * MAX_COLS + col
interface Cell { raw: string; value: unknown; ast?: Ast; }
interface Model { cells: Map<Key, Cell>; deps: Map<Key, Set<Key>>; precs: Map<Key, Set<Key>>; }

function recalcFrom(m: Model, changed: Key): Key[] {
  const order: Key[] = []; const done = new Set<Key>(); const onStack = new Set<Key>();
  const visit = (k: Key) => {
    if (done.has(k)) return;
    if (onStack.has(k)) throw new CycleError(k);
    onStack.add(k);
    for (const d of m.deps.get(k) ?? []) visit(d);
    onStack.delete(k); done.add(k); order.push(k);
  };
  visit(changed);
  order.reverse(); // changed first, then dependents in dependency order
  for (const k of order) {
    const c = m.cells.get(k);
    if (c?.ast) c.value = evaluate(c.ast, ref => m.cells.get(ref)?.value ?? null);
  }
  return order; // keys whose values may have changed → post to main thread
}

function rowAt(offsetPx: number, prefix: Float64Array): number { // binary search in cumulative heights
  let lo = 0, hi = prefix.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (prefix[mid] <= offsetPx) lo = mid + 1; else hi = mid; }
  return lo;
}
```
(Prefix sums over 1M rows are fine in a typed array; for sparse overrides, a Fenwick tree keeps resize updates O(log n).)

## Trade-offs & pitfalls
- DOM grid: native text selection, a11y, simpler; struggles past a few thousand visible-ish nodes and fast scroll. Canvas: smooth at any size; you rebuild text layout, hit testing, a11y.
- Worker boundary: model lives in worker, so reads (e.g. render) use a value cache synced via messages; structured clone costs on large diffs (consider transferables/SharedArrayBuffer with COOP/COEP).
- Range edges: naive per-cell edges for `SUM(A1:A100000)` blow memory and recalc time.
- CRDT vs server-ordered ops: CRDTs handle cell values well but structural ops + reference rewriting are easier with a central order.
- Floating point display vs storage; locale-specific number parsing on paste.

## Likely follow-ups
- *Formula parser?* Tokenizer + Pratt/recursive-descent parser → AST; cache AST per cell; references extracted at parse.
- *How does undo work with collaborators?* Only your inverse ops, transformed so they apply to current state; if target was deleted, undo becomes a no-op.
- *Cross-sheet refs?* Graph spans sheets with sheet-qualified keys; lazy-load sheets but keep their dependency index.
- *Saving?* Op log + periodic snapshots server-side; client loads snapshot + tail ops.
- *Testing?* Property tests on recalc (random edits vs naive full recompute), golden tests for formula semantics vs a reference spreadsheet.

## Say it in 60 seconds
I'd model the sheet as a sparse map of cells, each holding raw input, computed value, parsed formula and format, with row and column sizes stored only as overrides. A formula engine parses once into an AST and maintains precedent and dependent edges, with ranges indexed as ranges. On edit it walks dependents in topological order, evaluates each once, and flags cycles. For big sheets the model and recalc run in a Web Worker that posts back changed values. Rendering is two-axis virtualization from prefix sums. At large scale that's canvas with a textarea overlay for editing and a small ARIA grid mirror for screen readers. Collaboration is server-ordered cell and structural operations with optimistic apply and rebase. Structural ops rewrite formula references, presence is coloured selections, and undo is a per-user stack of transformed inverse ops.
