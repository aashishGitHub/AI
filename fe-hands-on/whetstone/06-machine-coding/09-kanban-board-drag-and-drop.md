# Build a Trello-style kanban board: lists, cards, drag and drop between lists, persisted on reload
**Round:** 06 · Machine Coding · **Level:** Lead / Staff · **Time:** 60 min · **Tags:** machine coding · kanban · drag and drop
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
Component structure and state shape that survive the next three feature requests (rename, labels, due dates), precise drop positions, a keyboard path, and robust persistence.

Tests: add card to "Todo" → bottom of that list; delete removes it everywhere; drag B from Todo to middle of Doing → inserted at that index, removed from Todo; drop in place → no change and no save; delete list → its cards gone from storage; reload restores everything; corrupted storage → empty board, no crash.

## Core answer (key points)
- **Say scope and order out loud:** no auth/server, one board, localStorage as DB. Order: state + reducer → UI → drag → persistence → keyboard.
- **Normalize state:** `listOrder: string[]`, `lists: Record<id, { id, title, cardIds[] }>`, `cards: Record<id, Card>`. A move touches two small arrays; nested `lists[].cards[]` makes moves rewrite a tree.
- **One pure reducer** for `addList`, `deleteList` (also deletes its cards — no orphans), `addCard`, `deleteCard`, `moveCard(cardId, toListId, toIndex)`. Ids created by the caller (`crypto.randomUUID()`) → reducer stays deterministic and unit-testable.
- **`moveCard` semantics:** `toIndex` is the position *after* removing the card from its source. Clamp. If the result equals the original order, **return the same reference** → no re-render, no save.
- **Drag is an input device, not state.** It only produces `(cardId, toListId, toIndex)`. Native HTML5 DnD: `draggable`, `dataTransfer.setData`, `dragover` **must `preventDefault`** or drop never fires.
- **Drop index** = first non-dragged card whose vertical midpoint is below the pointer; none → append. Excluding the dragged card yields the after-removal index (fixes off-by-one moving down within a list).
- **Persistence:** versioned key (`board:v1`), debounced save effect, load through a type guard that validates referential integrity; any parse/validation failure → empty board. Wrap `setItem` for quota/private mode.
- **Keyboard/AT path:** a "Move to…" select per card (or arrow-key move mode with live-region announcements like "Moved to Doing, position 2 of 4"). WCAG 2.5.7 requires a non-drag alternative.
- **Production:** dnd-kit (pointer/touch/keyboard sensors) — native DnD is mouse-only and unreliable on mobile.

## Mental model / flow
```
<Board>  useReducer(reduce, undefined, loadBoard)  + debounced save effect
 ├─ <List id> × listOrder         onDragOver(preventDefault) onDrop → dropIndex → moveCard
 │   ├─ <Card id> × cardIds       draggable, onDragStart(setData id), Move-to select, Delete
 │   └─ <AddCardForm listId>
 └─ <AddListForm>
transient UI state (draggingId) lives outside the persisted board
```

## Code sketch
```ts
export type Board = { listOrder: string[]; lists: Record<string, Col>; cards: Record<string, Card> };
type Col = { id: string; title: string; cardIds: string[] };
type Card = { id: string; title: string };

export type Action =
  | { type: 'addList'; id: string; title: string }
  | { type: 'deleteList'; listId: string }
  | { type: 'addCard'; id: string; listId: string; title: string }
  | { type: 'deleteCard'; cardId: string }
  | { type: 'moveCard'; cardId: string; toListId: string; toIndex: number };

const without = <T>(rec: Record<string, T>, ids: string[]) =>
  Object.fromEntries(Object.entries(rec).filter(([k]) => !ids.includes(k)));

export function reduce(b: Board, a: Action): Board {
  switch (a.type) {
    case 'addList':
      return { ...b, listOrder: [...b.listOrder, a.id], lists: { ...b.lists, [a.id]: { id: a.id, title: a.title, cardIds: [] } } };
    case 'deleteList': {
      const col = b.lists[a.listId];
      if (!col) return b;
      return { listOrder: b.listOrder.filter(id => id !== a.listId),
               lists: without(b.lists, [a.listId]), cards: without(b.cards, col.cardIds) };
    }
    case 'addCard': {
      const col = b.lists[a.listId];
      if (!col) return b;
      return { ...b, cards: { ...b.cards, [a.id]: { id: a.id, title: a.title } },
               lists: { ...b.lists, [col.id]: { ...col, cardIds: [...col.cardIds, a.id] } } };
    }
    case 'deleteCard': {
      const col = Object.values(b.lists).find(l => l.cardIds.includes(a.cardId));
      if (!col) return b;
      return { ...b, cards: without(b.cards, [a.cardId]),
               lists: { ...b.lists, [col.id]: { ...col, cardIds: col.cardIds.filter(id => id !== a.cardId) } } };
    }
    case 'moveCard': {
      const from = Object.values(b.lists).find(l => l.cardIds.includes(a.cardId));
      const to = b.lists[a.toListId];
      if (!from || !to) return b;
      const stripped = from.cardIds.filter(id => id !== a.cardId);
      const base = from.id === to.id ? stripped : to.cardIds;
      const i = Math.max(0, Math.min(a.toIndex, base.length));
      const placed = [...base.slice(0, i), a.cardId, ...base.slice(i)];
      if (from.id === to.id && placed.join() === from.cardIds.join()) return b; // no-op: same ref
      return { ...b, lists: { ...b.lists, [from.id]: { ...from, cardIds: from.id === to.id ? placed : stripped },
                                           [to.id]: { ...to, cardIds: placed } } };
    }
  }
}

export function dropIndex(listEl: HTMLElement, y: number) {
  const cards = [...listEl.querySelectorAll<HTMLElement>('[data-card]:not([data-dragging])')];
  const i = cards.findIndex(c => { const r = c.getBoundingClientRect(); return y < r.top + r.height / 2; });
  return i < 0 ? cards.length : i;
}

const KEY = 'board:v1';
const isBoard = (v: unknown): v is Board => {
  const b = v as Board;
  return !!b && Array.isArray(b.listOrder) && typeof b.lists === 'object' && typeof b.cards === 'object'
    && b.listOrder.every(id => b.lists[id]?.cardIds?.every(c => c in b.cards));
};
export const load = (): Board => {
  try { const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? 'null'); return isBoard(v) ? v : empty(); }
  catch { return empty(); }
};
```
```tsx
function useBoard() {
  const [board, dispatch] = useReducer(reduce, undefined, load);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }        // don't rewrite what we just loaded
    const t = setTimeout(() => { try { localStorage.setItem(KEY, JSON.stringify(board)); } catch {} }, 200);
    return () => clearTimeout(t);
  }, [board]);                                                    // no-op move → same ref → effect skipped
  return [board, dispatch] as const;
}
```
Card row outline: `<li data-card draggable onDragStart onDragEnd>` + title + `<select aria-label={`Move "${title}" to`}>` dispatching `moveCard(toIndex: Infinity)` (append) + delete button with descriptive `aria-label`. Memoize `CardView` by id; the reducer preserves untouched card objects so memo holds.

## Trade-offs & pitfalls
- Same-list move bug: building `to` from the original array instead of `stripped` duplicates the card.
- `deleteCard` scanning all lists is O(lists × cards); pass `listId` or keep a `cardToList` index if boards get big.
- Persisting `draggingId` or DOM indexes into the board = bugs on reload.
- Multiple tabs: listen to `storage` event and reload, or declare last-write-wins.
- Storage is untrusted input: never `JSON.parse` straight into state.

## Likely follow-ups
- **Reorder lists?** `moveList` mirroring `moveCard` on `listOrder`.
- **Server persistence?** Optimistic dispatch, send the action, roll back on failure; fractional-index `rank` per card so concurrent moves don't renumber.
- **Undo?** Wrap the reducer with the history reducer from Q05.
- **Real-time collaboration?** Ship actions as ops; server ordering or CRDT; the pure reducer is what you replay.
- **1,000 cards per list?** Virtualize each list (Q02); reducer unchanged.

## Say it in 60 seconds
I'd state the scope, then normalize state: an ordered list of list ids, lists that hold ordered card ids, and a card map, so a move touches only two arrays. Every change goes through one pure reducer, and `moveCard` takes a target list and an after-removal index and returns the same reference when nothing changed, so a drop in place doesn't re-render or save. Deleting a list deletes its cards. Drag and drop is just input: native events compute the index from the pointer against card midpoints, excluding the dragged card, and dispatch `moveCard`. Persistence is a versioned, debounced localStorage write, and loading goes through a validator that falls back to an empty board. Every card also has a "Move to" select because drag isn't keyboard or screen-reader accessible, and in production I'd use dnd-kit.
