# Add undo/redo to an editor: command pattern vs snapshots, coalescing, and limits
**Round:** 06 · Machine Coding · **Level:** Lead / Staff · **Time:** 30 min · **Tags:** undo · redo · command pattern
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
Undo/redo for a drawing or text editor: compare snapshots vs commands, implement one with a history limit and coalescing of rapid edits, keyboard shortcuts, `canUndo/canRedo`.

Tests: apply A, B, C → undo ×2 → A; redo → B. Apply A, B, undo, apply D → `canRedo=false`, history A, D. Ten keystrokes within 500 ms → one undo step. Limit 50 → 51st edit drops the oldest; undo never goes past it.

## Core answer (key points)
- **Snapshots:** `{ past[], present, future[] }`. Trivial with immutable state; structural sharing keeps memory proportional to *changes*, not doc size × steps. Easiest to debug (time travel).
- **Commands/patches:** store operations with `apply` + `invert` (or Immer `produceWithPatches` → patches + inverse patches). Compact; required for collaboration (undo *your* ops, not others'), but each op needs a correct inverse.
- **Rules regardless of approach:**
  - New edit after undo **clears redo**.
  - **Coalesce** bursts: same `coalesceKey` (e.g. `text:field42`) within a window → replace present without pushing to past.
  - **Cap** history (`past.slice(-LIMIT)`).
  - **Transactions:** a drag producing 60 moves = one step (`begin`/`commit`).
  - Decide what's **not undoable**: selection, scroll, viewport, server side effects (or delay them, like "undo send").
  - Store **selection** with entries so undo restores the cursor.
- **Shortcuts:** Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z, Ctrl+Y; don't hijack inside native text inputs that have their own undo stack.

## Mental model / flow
```
past        present   future
[A]         B         []        edit C  → [A,B]  C  []
[A,B]       C         []        undo    → [A]    B  [C]
[A]         B         [C]       edit D  → [A,B]  D  []      (redo cleared)
coalesce: edit within 500ms same key → present replaced, past unchanged
```

## Code sketch
```ts
type Hist<T> = { past: T[]; present: T; future: T[]; key: string | null; at: number };
type Act<T> =
  | { type: 'commit'; next: T; key?: string; now: number }
  | { type: 'undo' } | { type: 'redo' } | { type: 'reset'; to: T };

export const makeHistory = <T>(limit = 50, windowMs = 500) =>
  function reducer(h: Hist<T>, a: Act<T>): Hist<T> {
    switch (a.type) {
      case 'commit': {
        if (Object.is(a.next, h.present)) return h;
        const merge = a.key != null && a.key === h.key && a.now - h.at < windowMs;
        const past = merge ? h.past : [...h.past, h.present];
        return { past: past.length > limit ? past.slice(past.length - limit) : past,
                 present: a.next, future: [], key: a.key ?? null, at: a.now };
      }
      case 'undo': {
        if (!h.past.length) return h;
        return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1],
                 future: [h.present, ...h.future], key: null, at: 0 };
      }
      case 'redo': {
        if (!h.future.length) return h;
        const [next, ...rest] = h.future;
        return { past: [...h.past, h.present], present: next, future: rest, key: null, at: 0 };
      }
      case 'reset': return { past: [], present: a.to, future: [], key: null, at: 0 };
    }
  };

// Command flavor (outline)
interface Command<D> { label: string; apply(d: D): D; inverse(before: D): Command<D> }
```
```tsx
function useUndoable<T>(initial: T) {
  const [h, dispatch] = useReducer(makeHistory<T>(), { past: [], present: initial, future: [], key: null, at: 0 });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest('input,textarea,[contenteditable]')) return;  // native undo wins there
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); dispatch({ type: e.shiftKey ? 'redo' : 'undo' }); }
      else if (e.ctrlKey && e.key.toLowerCase() === 'y') { e.preventDefault(); dispatch({ type: 'redo' }); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return {
    value: h.present, canUndo: h.past.length > 0, canRedo: h.future.length > 0,
    set: (next: T, key?: string) => dispatch({ type: 'commit', next, key, now: performance.now() }),
    undo: () => dispatch({ type: 'undo' }), redo: () => dispatch({ type: 'redo' }),
  };
}
```
Tests run directly on the reducer with an injected `now` — no timers or DOM needed.

## Trade-offs & pitfalls
| | Snapshots | Commands / patches |
|---|---|---|
| Effort | Low | Higher (correct inverses) |
| Memory | Grows with change size (structural sharing) | Small |
| Collaboration | Breaks (reverts others' work) | Works with OT/CRDT transforms |
| Debug | Time travel | Labels for Edit menu ("Undo move 3 shapes") |
- Mutating state anywhere breaks snapshots silently; enforce immutability (Immer, freeze in dev).
- Coalescing by time only merges unrelated edits; include a semantic key (field, tool).
- `Date.now()` for windows can jump; `performance.now()` is monotonic.
- Limit applies to `past`; also bound `future` if redo branches can be huge (they're bounded by past anyway).

## Likely follow-ups
- **Undo in a collaborative editor?** Per-user op history; invert your op and transform it against concurrent ops (Yjs has an `UndoManager`).
- **Persist history across reloads?** Store patches, not snapshots; cap by size.
- **Branching history?** Undo tree (Vim/Emacs style); usually overkill for product UI.
- **Undo for server mutations?** Optimistic local undo + compensating API call, or delayed commit window.

## Say it in 60 seconds
There are two models. Snapshots keep past, present and future states; with immutable data and structural sharing it's cheap and trivial to debug. Commands or patches store operations with inverses; they're compact and the only option for collaboration, but every inverse must be right. I'd implement snapshots as a reducer: a commit pushes present onto past, clears the redo stack and caps past at the limit; edits with the same coalesce key inside a time window replace present instead of adding a step, so a typing burst is one undo. Undo and redo just move entries between stacks. I add transactions for drags, keep selection and server side effects out of history, and wire Cmd/Ctrl+Z without hijacking native inputs.
