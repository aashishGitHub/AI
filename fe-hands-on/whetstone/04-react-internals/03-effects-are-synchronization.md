# Effects are synchronization, not lifecycle: when don't you need useEffect?
**Round:** 04 · React Rendering & Internals · **Level:** Senior · **Time:** 15 min · **Tags:** useeffect · derived state · events
Source: https://whetstone-v1.vercel.app/#react-internals

## What they're really testing
Code-review judgment: can you spot effects that should not exist (fetch, prop mirroring, reset-on-id, manual store subscription) and name the right replacement for each?

## Core answer (key points)
- `useEffect` is for keeping React in sync with something **outside** React: DOM APIs, subscriptions, sockets, timers, third-party widgets, network.
- Decision rule:
  - Caused by a user action → **event handler**.
  - Computable from props/state → **compute during render** (`useMemo` if expensive).
  - Reset when a prop changes → **`key`** the component, or adjust state during render.
  - Subscribing to an external store → **`useSyncExternalStore`**.
  - Fetching → a **data library** (TanStack Query, SWR, RTK Query), framework loader, or `use()` with a cached promise.
- Removing unnecessary effects removes their bugs: extra renders, effect chains, loops, races.
- **Strict Mode** (dev) mounts → unmounts → mounts to prove your cleanup is correct. If it breaks, the effect is missing cleanup or isn't idempotent.

## Mental model / flow
| Smell | Replacement |
|---|---|
| effect sets `fullName` from `first`/`last` | `const fullName = ...` in render |
| effect filters items into state | `useMemo(() => filter(items), [items])` |
| effect posts when `submitted` flips | call `post()` in submit handler |
| effect clears selection when `items` change | store `selectedId`, derive selection; or `key` |
| effect calls `onChange(value)` | call `onChange` in the handler that changed value |
| chain of effects setting state | one handler computing next state |

## Code sketch
```tsx
// Derive, don't sync: a vanished selection simply resolves to null
function Picker({ items }: { items: Item[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find(i => i.id === selectedId) ?? null;
  return <List items={items} selected={selected} onSelect={setSelectedId} />;
}

// Rare case: reset state on prop change without an effect
function Pager({ query }: { query: string }) {
  const [page, setPage] = useState(1);
  const [lastQuery, setLastQuery] = useState(query);
  if (query !== lastQuery) {
    setLastQuery(query);
    setPage(1); // React re-runs this render before children see stale page
  }
  // ...
}

// Legitimate effect: external system, with cleanup
function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}
```
(For `useOnline`, `useSyncExternalStore` is the better fit: no extra render, no tearing.)

## Trade-offs & pitfalls
- Fetch-in-effect forces you to hand-roll race handling (ignore flag / AbortController), caching, dedupe, retries.
- Disabling `exhaustive-deps` hides stale closures; if adding a dep causes a loop, the effect is doing too much.
- "Set state during render" must be guarded by a comparison or it loops.
- `key` reset also remounts children and refires their effects; fine for forms, costly for heavy trees.

## Likely follow-ups
- **Read latest props in an effect without re-running it?** `useEffectEvent` (I believe it is stable as of React 19.2; verify) or the older latest-ref pattern.
- **Why does the lint rule demand every dep?** Missing deps = stale closure. Restructure instead of suppressing.
- **Why does my fetch run twice in dev?** Strict Mode double mount; add cleanup/abort, or move to a data library that dedupes.
- **Is `useEffect` for analytics on mount okay?** Page-view style sync with an external system, yes; "user clicked buy" belongs in the handler.

## Say it in 60 seconds
I treat `useEffect` as synchronization with something outside React, not as lifecycle. If code responds to a user action, it goes in the handler. If it's derived from props or state, I compute it in render. If state must reset when an id changes, I key the component. Store subscriptions use `useSyncExternalStore`, and data fetching goes through a library or framework loader that handles races and caching. What's left are real effects like subscribing to a browser API, which must have symmetric cleanup, and Strict Mode's double mount in dev is how I verify that cleanup works.
