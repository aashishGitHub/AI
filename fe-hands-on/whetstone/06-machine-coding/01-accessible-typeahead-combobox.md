# Build an accessible typeahead (combobox) with debounced search and race-safe results
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 45 min · **Tags:** machine coding · combobox · autocomplete
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
45-minute build of a user-directory search box against `search(query, signal)`. Min 2 chars, ~250 ms debounce, stale responses never overwrite newer ones, loading/empty/error states, ARIA 1.2 combobox, focus stays in the input, Arrow/Enter/Escape.

Tests: `a` → no call; `al` → one call after debounce; `al` then `ali` fast → only `ali` results even if `al` resolves last; ArrowDown ×2 + Enter selects option 2 and calls `onSelect`; Escape closes and keeps text; rejected request → error + retry; zero results → "No matches".

## Core answer (key points)
- **Clarify (2 min):** free text allowed or must pick? Min chars, delay, max results? Highlight match? Recent searches on empty focus? Mobile?
- **State:** `query`, `open`, `activeIndex` (-1 none), and a fetch slice `{ status, results, forQuery }`.
- **Data flow:** query → effect keyed on trimmed query → `setTimeout(delay)` → `search(q, controller.signal)` → write result. Cleanup clears the timer **and** aborts the controller. One cleanup gives you both debounce and latest-wins.
- **Belt and braces for races:** also tag results with `forQuery` and ignore writes where `forQuery !== latestQuery` in case the search function ignores the signal.
- **Cache** `Map<query, results>` for instant back-spacing.
- **ARIA 1.2:** input `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"`, `aria-activedescendant`; `ul role="listbox"` with `li role="option" aria-selected`. Focus never leaves the input.
- **Live region** announces "N results" once results settle, not per keystroke.
- **Option `onMouseDown` → `preventDefault`** so input blur doesn't close the list before click lands.
- **Highlight** with `<mark>` elements, never `innerHTML` (XSS from labels).
- **Keep previous results visible while loading** to avoid flicker; reset `activeIndex` when results change.
- **Retry:** store last failed query; a Retry button re-runs it (bump a `retryToken` dep).

## Mental model / flow
```
keystroke → query state
  effect(q):
    q.length < 2      → idle, clear
    cache.has(q)      → success(cached)
    else              → timer(250) → loading → search(q, signal)
                                   → success | error (ignore if aborted)
  cleanup             → clearTimeout + abort      (next keystroke)
keys: ↓/↑ move activeIndex (wrap) · Enter select · Esc close (2nd Esc clears)
```

## Code sketch
Component structure (outline, original):
```tsx
type Status = 'idle' | 'loading' | 'success' | 'error';

function useLatestSearch<T>(q: string, search: (q: string, s: AbortSignal) => Promise<T[]>, retry: number) {
  const [res, setRes] = useState<{ status: Status; items: T[] }>({ status: 'idle', items: [] });
  const cache = useRef(new Map<string, T[]>());
  const fn = useRef(search);
  useLayoutEffect(() => { fn.current = search; });

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setRes({ status: 'idle', items: [] }); return; }
    const hit = cache.current.get(term);
    if (hit) { setRes({ status: 'success', items: hit }); return; }

    const ac = new AbortController();
    const t = setTimeout(() => {
      setRes(r => ({ ...r, status: 'loading' }));         // keep old items visible
      fn.current(term, ac.signal).then(
        items => { if (!ac.signal.aborted) { cache.current.set(term, items); setRes({ status: 'success', items }); } },
        () => { if (!ac.signal.aborted) setRes({ status: 'error', items: [] }); },
      );
    }, 250);
    return () => { clearTimeout(t); ac.abort(); };
  }, [q, retry]);

  return res;
}

export function UserSearch({ search, onSelect }: { search: Search; onSelect: (u: User) => void }) {
  const id = useId();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [retry, setRetry] = useState(0);
  const { status, items } = useLatestSearch(q, search, retry);
  // reset highlight when items change: compare-in-render pattern, not an effect

  const pick = (u: User) => { setQ(u.name); setOpen(false); onSelect(u); };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => { /* ↓ ↑ wrap, Enter pick(items[active]), Esc */ };

  const listOpen = open && q.trim().length >= 2;
  return (
    <div>
      <label htmlFor={`${id}-in`}>Find a person</label>
      <input id={`${id}-in`} role="combobox" aria-expanded={listOpen} aria-controls={`${id}-lb`}
        aria-autocomplete="list" aria-activedescendant={listOpen && active >= 0 ? `${id}-o${active}` : undefined}
        autoComplete="off" value={q} onKeyDown={onKeyDown} onBlur={() => setOpen(false)}
        onChange={e => { setQ(e.target.value); setOpen(true); }} />
      <div role="status" aria-live="polite" className="sr-only">
        {listOpen && status === 'success' ? `${items.length} results` : ''}
      </div>
      {listOpen && (
        <ul id={`${id}-lb`} role="listbox" aria-label="People">
          {status === 'error' && <li role="presentation">Search failed <button onMouseDown={e => e.preventDefault()} onClick={() => setRetry(n => n + 1)}>Retry</button></li>}
          {status === 'success' && items.length === 0 && <li role="presentation">No matches</li>}
          {items.map((u, i) => (
            <li key={u.id} id={`${id}-o${i}`} role="option" aria-selected={i === active}
                onMouseDown={e => e.preventDefault()} onMouseMove={() => setActive(i)} onClick={() => pick(u)}>
              <Mark text={u.name} term={q} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```
Tests: fake timers; `user.type(input, 'al')` → advance 250 ms → `expect(search).toHaveBeenCalledTimes(1)`; resolve `al` after `ali` with deferred promises → assert only `ali` items; keyboard by role.

## Trade-offs & pitfalls
- Debounce in the handler (lodash) + separate fetch effect = two places to reason about; effect cleanup is simpler.
- Setting `loading` synchronously on each keystroke flickers; set it when the timer fires.
- A Retry button inside the listbox is interactive content inside `role=listbox`, which is not ideal semantically; alternatively place retry outside the popup. I'm not certain which screen readers handle the inline version well.
- `scrollIntoView({ block: 'nearest' })` for the active option in long lists.
- IME composition (`compositionstart/end`) and iOS VoiceOver quirks are why production uses Downshift / React Aria `useComboBox`.

## Likely follow-ups
- **Why abort if you already ignore stale?** Saves bandwidth and server load; ignoring alone still races if the fetch has no tag.
- **Server-side ranking vs client filtering?** Directory is large → server; client only highlights.
- **Large result sets?** Virtualize the listbox; keep `aria-setsize`/`aria-posinset`.
- **i18n matching?** `Intl.Collator` with `sensitivity: 'base'` and diacritic folding.

## Say it in 60 seconds
I'd clarify free text vs must-pick, min characters and debounce, then model query, open, active index and a fetch status. The data hook runs an effect per trimmed query: under two characters it clears, cached queries return instantly, otherwise it waits 250 ms and calls `search` with an AbortSignal. The cleanup clears the timer and aborts, so the latest keystroke always wins and stale responses can't land. The input is an ARIA 1.2 combobox with `aria-activedescendant` pointing at the highlighted option, so focus never leaves it; options prevent mousedown so blur doesn't eat the click. A polite live region announces the result count, highlights use `<mark>` not innerHTML, and error, empty and loading states are explicit with a retry.
