# Design search with autocomplete at scale (frontend side): caching, ranking display and latency
**Round:** 12 · Frontend System Design · **Level:** Senior · **Time:** 20 min · **Tags:** system design · search · autocomplete
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: large e-commerce site; suggestions as you type, recent searches, categories and products, slow mobile networks.

## What they're really testing
Request racing (debounce, abort, dedupe), prefix caching and local filtering, perceived-latency tricks, accessible combobox, safe highlighting, and feedback loops for ranking.

## Core answer (key points)
- **Requirements:** suggestions after 1-2 chars, perceived latency < ~100ms, keyboard nav, recent searches, grouped categories (products, categories, help), match highlighting, mobile-first.
- **Request pipeline:**
  - `normalize(q)` (trim, lowercase, collapse spaces, maybe strip diacritics) → cache key.
  - **LRU cache by prefix** in memory; optionally persist popular prefixes in IndexedDB.
  - **Debounce lightly** (0-150ms; with a fast backend, zero plus abort is fine).
  - **Abort** the previous in-flight request (`AbortController`); **dedupe** identical in-flight queries; and guard against out-of-order responses (only apply if response matches current query).
  - **Prefix reuse:** if the server marks results for `reac` as exhaustive, filter locally for `react`.
- **Latency tricks:** `preconnect` to the search origin on load or input focus; CDN-cache anonymous prefix responses with short TTL and merge personalization client-side; keep previous results visible while loading; delay spinner ~200ms to avoid flicker.
- **Rendering:** grouped sections with headings (`role="group"` inside listbox), fixed row heights (no layout shift), highlight by splitting text into React nodes on the client from match offsets (never server `innerHTML`).
- **Accessibility:** APG combobox: `<input role="combobox" aria-expanded aria-controls aria-activedescendant>`, `role="listbox"`/`option`, arrow keys move active option while focus stays in the input, Enter selects, Escape closes; polite live region announces result count after results settle.
- **Recent searches:** localStorage, max ~10, user-clearable, shown on empty focus.
- **State:** results page query in the URL (`/search?q=`), shareable and back-button friendly.
- **Failure modes:** suggestion timeout (~800ms) → fall back to recent searches; Enter always submits a full search regardless of suggestion state.
- **Analytics:** sampled, privacy-aware logs of query, suggestions shown (with ranking version id), position clicked, time-to-click, abandonment; enables ranking A/B tests.

## Mental model / flow
```
            keystroke
                │
                ▼
  Input ── normalize(q) ──► SuggestCache (LRU by prefix)
    │                          │ hit ───────────────────────────────┐
    │                          │ miss                                │
    │                          ▼                                     │
    │          exhaustive parent prefix cached? ─ yes ─► filter local┤
    │                          │ no                                  │
    │                          ▼                                     │
    │          RequestManager: debounce 0-150ms · abort prev ·       │
    │                          dedupe in-flight · timeout 800ms      │
    │                          │                                     │
    │                          ▼                                     │
    │          GET /suggest?q=&locale=  (CDN, short TTL, anon)       │
    │                          │ response (q matches current?)       │
    │                          ▼                                     ▼
    │                      cache.set ──────────────► Render listbox (grouped, fixed rows,
    │                                                safe highlight) + live-region count
    ├─► on focus (empty): RecentSearches (localStorage)
    └─► Enter: navigate /search?q=… (always allowed) ─► log {q, shown, version, pos}
```

## Code sketch
```tsx
const cache = new Map<string, { items: Suggestion[]; exhaustive: boolean }>(); // insertion-ordered → simple LRU
const LIMIT = 200;
let ctl: AbortController | null = null;

export async function suggest(raw: string): Promise<Suggestion[]> {
  const q = raw.trim().toLowerCase().replace(/\s+/g, ' ');
  const hit = cache.get(q);
  if (hit) { cache.delete(q); cache.set(q, hit); return hit.items; }
  for (let i = q.length - 1; i > 0; i--) {
    const parent = cache.get(q.slice(0, i));
    if (parent?.exhaustive) return parent.items.filter(s => s.label.toLowerCase().includes(q));
  }
  ctl?.abort(); ctl = new AbortController();
  const timeout = setTimeout(() => ctl?.abort(), 800);
  try {
    const res = await fetch(`/suggest?q=${encodeURIComponent(q)}`, { signal: ctl.signal });
    const body = await res.json() as { items: Suggestion[]; exhaustive: boolean };
    cache.set(q, body); if (cache.size > LIMIT) cache.delete(cache.keys().next().value!);
    return body.items;
  } finally { clearTimeout(timeout); }
}

export const highlight = (label: string, q: string) => {
  const i = label.toLowerCase().indexOf(q);
  return i < 0 ? [label] : [label.slice(0, i), <mark key="m">{label.slice(i, i + q.length)}</mark>, label.slice(i + q.length)];
};
```
(Caller must still check the response belongs to the latest input before rendering; the AbortError from a superseded request should be swallowed.)

## Trade-offs & pitfalls
- Debounce adds fixed latency to every keystroke; abort-only is snappier but costs more requests. Tune with real backend p50/p95.
- Local filtering only valid if the server guarantees completeness for that prefix (and ranking may differ).
- Personalised suggestions can't be CDN-cached; split anon (cacheable) and personal (client merge).
- Recent searches in localStorage are visible on shared devices; offer clear and respect private contexts.
- Moving DOM focus into the list breaks typing; use `aria-activedescendant`.
- Logging raw queries can capture PII (emails, phone numbers typed into search); sample and scrub.

## Likely follow-ups
- *Typo tolerance?* Server-side (fuzzy/n-gram); client only displays; can show "did you mean".
- *Mobile specifics?* Larger touch rows, `enterkeyhint="search"`, `inputmode`, avoid auto-zoom (font-size ≥ 16px on iOS).
- *Prefetching?* Warm likely next prefixes or the top suggestion's results page on hover/arrow.
- *How to test relevance and perf?* Offline relevance sets + online A/B on CTR/zero-result rate; RUM for suggestion latency p75; Playwright with throttled network for race conditions.

## Say it in 60 seconds
The frontend's job is to make suggestions feel instant and correct. I normalize the query, check an in-memory LRU keyed by prefix, and if a shorter prefix's results were marked exhaustive I filter those locally. On a miss, I debounce lightly or not at all, abort the previous request, dedupe in-flight queries and ignore out-of-order responses. Anonymous suggest responses are CDN-cacheable with a short TTL, I preconnect on focus, keep old results visible while loading and delay any spinner. Results render in grouped, fixed-height rows with client-side highlighting, never server HTML. It's the APG combobox: focus stays in the input via `aria-activedescendant`, and a polite region announces counts. On timeout I fall back to recent searches, and Enter always runs a full search. I log impressions and clicks with the ranking version so relevance experiments are measurable.
