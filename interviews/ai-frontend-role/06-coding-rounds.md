# 06 · Coding rounds: write these from a blank file

Practise: close this file, 25-minute timer, write it in `scratch.ts`, run with `npx tsx scratch.ts` (or `node --experimental-strip-types` on Node 22.6+; verify your Node version).
More machine-coding prompts with notes: [whetstone/03 async utilities](../../fe-hands-on/whetstone/03-async-utilities/README.md) ·
[whetstone/06 machine coding](../../fe-hands-on/whetstone/06-machine-coding/README.md) · drills with tests: [`devrev-fde/drills/ts/`](../devrev-fde/drills/ts/).

Each solution lists **what the interviewer is checking**. Say those out loud while you code.

---

## C1. SSE parser over fetch

**Checking:** chunk ≠ event, UTF-8 split across chunks, CRLF split across chunks, multi-line `data`, comments, early exit cleanup.

```ts
export type SSEEvent = { event: string; data: string; id?: string };

export function createSSEParser() {
  let buffer = '';
  let data: string[] = [];
  let eventType = '';
  let lastId: string | undefined;

  function processLine(line: string, out: SSEEvent[]) {
    if (line === '') {
      if (data.length > 0) out.push({ event: eventType || 'message', data: data.join('\n'), id: lastId });
      data = [];
      eventType = '';
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') data.push(value);
    else if (field === 'event') eventType = value;
    else if (field === 'id') lastId = value;
  }

  return {
    feed(text: string): SSEEvent[] {
      buffer += text;
      // A trailing '\r' may be the first half of '\r\n' arriving in the next chunk.
      let hold = '';
      let chunk = buffer;
      if (chunk.endsWith('\r')) {
        hold = '\r';
        chunk = chunk.slice(0, -1);
      }
      const lines = chunk.split(/\r\n|\r|\n/);
      buffer = (lines.pop() ?? '') + hold;
      const out: SSEEvent[] = [];
      for (const line of lines) processLine(line, out);
      return out;
    },
  };
}

export async function* readSSE(res: Response): AsyncGenerator<SSEEvent> {
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser();
  let finished = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      yield* parser.feed(decoder.decode(value, { stream: true }));
    }
    yield* parser.feed(decoder.decode());
    finished = true;
  } finally {
    if (!finished) await reader.cancel().catch(() => {});
  }
}
```
Talking points: per the SSE spec an unterminated final event (no blank line before EOF) is **discarded**; some clients flush it leniently — choose one and test it. `retry:` field omitted for brevity. `TextDecoderStream` + `pipeThrough` is the stream-native alternative.

**Tests (Vitest):**
```ts
import { it, expect } from 'vitest';
import { createSSEParser } from './sse';

it('joins an event split across chunks, with multi-line data', () => {
  const p = createSSEParser();
  expect(p.feed('event: token\ndata: hel')).toEqual([]);
  expect(p.feed('lo\ndata: world\n\n')).toEqual([{ event: 'token', data: 'hello\nworld', id: undefined }]);
});

it('treats a CRLF split across chunks as one line ending', () => {
  const p = createSSEParser();
  expect(p.feed('data: a\r')).toEqual([]);
  expect(p.feed('\n\r\n')).toEqual([{ event: 'message', data: 'a', id: undefined }]);
});

it('ignores comment lines (heartbeats)', () => {
  const p = createSSEParser();
  expect(p.feed(': ping\n\ndata: x\n\n')).toEqual([{ event: 'message', data: 'x', id: undefined }]);
});
```

---

## C2. `useChatStream` hook: send, stop, rAF batching, no stale updates

**Checking:** abort on stop/unmount/new send, abort ≠ error, keep partial text, one render per frame, an old request can't overwrite a new one.

```tsx
import { useCallback, useEffect, useRef, useState } from 'react';
import { readSSE } from './sse';

type Status = 'idle' | 'streaming' | 'done' | 'stopped' | 'error';

export function useChatStream(url: string) {
  const [text, setText] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const ctrlRef = useRef<AbortController | null>(null);
  const pending = useRef('');
  const rafId = useRef<number | null>(null);

  const flush = useCallback(() => {
    rafId.current = null;
    const chunk = pending.current;
    pending.current = '';
    if (chunk) setText(t => t + chunk);
  }, []);

  const flushNow = useCallback(() => {
    if (rafId.current !== null) cancelAnimationFrame(rafId.current);
    flush();
  }, [flush]);

  const send = useCallback(async (prompt: string) => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const isCurrent = () => ctrlRef.current === ctrl;

    if (rafId.current !== null) cancelAnimationFrame(rafId.current);
    rafId.current = null;
    pending.current = '';
    setText('');
    setStatus('streaming');

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
        signal: ctrl.signal,
      });
      for await (const evt of readSSE(res)) {
        if (ctrl.signal.aborted) break;
        if (evt.event === 'token') {
          pending.current += (JSON.parse(evt.data) as { text: string }).text;
          if (rafId.current === null) rafId.current = requestAnimationFrame(flush);
        } else if (evt.event === 'error') {
          throw new Error((JSON.parse(evt.data) as { message: string }).message);
        } else if (evt.event === 'done') {
          break;
        }
      }
      if (!isCurrent()) return;
      flushNow();
      setStatus(ctrl.signal.aborted ? 'stopped' : 'done');
    } catch (err) {
      if (!isCurrent()) return;
      flushNow();
      setStatus(ctrl.signal.aborted ? 'stopped' : 'error');
    } finally {
      if (isCurrent()) ctrlRef.current = null;
    }
  }, [url, flush, flushNow]);

  const stop = useCallback(() => ctrlRef.current?.abort(), []);

  useEffect(() => () => {
    ctrlRef.current?.abort();
    if (rafId.current !== null) cancelAnimationFrame(rafId.current);
  }, []);

  return { text, status, send, stop };
}
```
Follow-ups: "Make it multi-message" → move to a reducer keyed by message ID (see [02 Q16](02-ai-frontend-engineering.md#q16--how-do-you-model-chat-state-on-the-client)). "Test it" → MSW handler returning a `ReadableStream` that enqueues chunks with delays; assert progressive text, then click Stop and assert status `stopped` with partial text.

---

## C3. Debounce with `cancel` and `flush`

**Checking:** last-call-wins args, timer cleanup, `this`-free API, typing.

```ts
export function debounce<A extends unknown[]>(fn: (...args: A) => void, waitMs: number) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let lastArgs: A | undefined;

  const invoke = () => {
    timer = undefined;
    const args = lastArgs!;
    lastArgs = undefined;
    fn(...args);
  };

  const debounced = (...args: A) => {
    lastArgs = args;
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(invoke, waitMs);
  };
  debounced.cancel = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    lastArgs = undefined;
  };
  debounced.flush = () => {
    if (timer === undefined) return;
    clearTimeout(timer);
    invoke();
  };
  return debounced;
}
```
Follow-ups: `maxWait` (fire at least every N ms during continuous typing), leading edge, a `useDebouncedCallback` hook (keep latest `fn` in a ref, cancel on unmount). Throttle vs debounce: throttle = at most once per interval (scroll/resize), debounce = after quiet period (search input).

---

## C4. Retry with exponential backoff, full jitter, `Retry-After`, and abort

**Checking:** which errors are retryable, jitter to avoid thundering herd, honour server hints, abortable sleep.

```ts
export class HttpError extends Error {
  constructor(public status: number, public retryAfterMs?: number) {
    super(`HTTP ${status}`);
  }
}

const isRetryable = (err: unknown) =>
  err instanceof HttpError ? err.status === 429 || err.status >= 500 : err instanceof TypeError; // fetch network failure = TypeError

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(t);
      reject(signal!.reason);
    };
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

export async function retry<T>(
  fn: (attempt: number) => Promise<T>,
  { retries = 3, baseMs = 300, maxMs = 10_000, signal }: { retries?: number; baseMs?: number; maxMs?: number; signal?: AbortSignal } = {},
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      if (signal?.aborted || attempt >= retries || !isRetryable(err)) throw err;
      const hinted = err instanceof HttpError ? err.retryAfterMs : undefined;
      const delay = hinted ?? Math.random() * Math.min(maxMs, baseMs * 2 ** attempt);
      await sleep(delay, signal);
    }
  }
}
```
Parse `Retry-After`: it's either seconds (`"30"`) or an HTTP date → `Number(h) * 1000` or `Date.parse(h) - Date.now()`.
Senior point: **never auto-retry a non-idempotent write** (send email, charge) unless it carries an idempotency key. Don't retry a stream that already delivered tokens without telling the user.

---

## C5. Concurrency-limited map (upload N files, max 3 at a time)

**Checking:** order of results preserved, never more than `limit` in flight, empty input.

```ts
export async function mapPool<T, R>(items: readonly T[], limit: number, fn: (item: T, index: number) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i], i);
    }
  }
  const workers = Array.from({ length: Math.min(limit, items.length) }, worker);
  await Promise.all(workers);
  return results;
}
```
`next++` is safe because JS is single-threaded between awaits. Behaviour on error: `Promise.all` rejects on the first failure but other workers keep running. Follow-ups: collect errors per item (allSettled style), cancellation with an `AbortSignal` checked in the loop, progress callback.

---

## C6. Latest-wins (cancel stale requests)

**Checking:** out-of-order responses can't overwrite newer state.

```ts
export function latestOnly<A extends unknown[], R>(fn: (signal: AbortSignal, ...args: A) => Promise<R>) {
  let current: AbortController | null = null;
  return (...args: A): Promise<R> => {
    current?.abort();
    const ctrl = new AbortController();
    current = ctrl;
    return fn(ctrl.signal, ...args);
  };
}
```
Caller ignores `AbortError`. Alternative when you can't abort (a library call): a sequence counter — `const id = ++seq; const r = await call(); if (id !== seq) return;`. In React, the effect-cleanup pattern does the same: `useEffect(() => { const c = new AbortController(); load(q, c.signal); return () => c.abort(); }, [q])`.

---

## C7. `Promise.all` and `Promise.allSettled` from scratch

```ts
export function promiseAll<T>(values: Iterable<T | PromiseLike<T>>): Promise<Awaited<T>[]> {
  return new Promise((resolve, reject) => {
    const items = Array.from(values);
    const out = new Array<Awaited<T>>(items.length);
    let remaining = items.length;
    if (remaining === 0) return resolve(out);
    items.forEach((v, i) => {
      Promise.resolve(v).then(r => {
        out[i] = r as Awaited<T>;
        if (--remaining === 0) resolve(out);
      }, reject);
    });
  });
}

export function promiseAllSettled<T>(values: Iterable<T | PromiseLike<T>>): Promise<PromiseSettledResult<Awaited<T>>[]> {
  return promiseAll(
    Array.from(values, v =>
      Promise.resolve(v).then(
        value => ({ status: 'fulfilled', value }) as PromiseFulfilledResult<Awaited<T>>,
        reason => ({ status: 'rejected', reason }) as PromiseRejectedResult,
      ),
    ),
  );
}
```
**Checking:** results in input order (not completion order), empty input resolves immediately, non-promise values accepted.

---

## C8. LRU cache with TTL + in-flight request dedupe

```ts
export class LruCache<K, V> {
  private map = new Map<K, { value: V; expiresAt: number }>();
  constructor(private max: number, private ttlMs: number, private now: () => number = Date.now) {}

  get(key: K): V | undefined {
    const entry = this.map.get(key);
    if (!entry) return undefined;
    if (entry.expiresAt <= this.now()) {
      this.map.delete(key);
      return undefined;
    }
    this.map.delete(key);
    this.map.set(key, entry);
    return entry.value;
  }

  set(key: K, value: V) {
    this.map.delete(key);
    this.map.set(key, { value, expiresAt: this.now() + this.ttlMs });
    if (this.map.size > this.max) this.map.delete(this.map.keys().next().value as K);
  }
}

const inflight = new Map<string, Promise<unknown>>();
export function dedupe<T>(key: string, load: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const p = load().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}
```
`Map` keeps insertion order, so delete + re-set moves a key to "most recent" and `keys().next()` is the least recent. Injected `now` makes TTL testable without fake timers.

---

## C9. Safe link for model-generated Markdown

```ts
const ALLOWED_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);

export function safeHref(raw: string, base: string): string | null {
  try {
    const url = new URL(raw, base);
    return ALLOWED_PROTOCOLS.has(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
```
Use it in the Markdown renderer's link component: `null` → render plain text. Extend with an image-host allowlist. **Checking:** you parse with `URL` instead of regex-matching `"javascript:"` (regexes miss `JaVaScRiPt:`, leading whitespace and encoded variants).

---

## C10. Typed event emitter

```ts
type Listener<T> = (payload: T) => void;

export class Emitter<Events extends Record<string, unknown>> {
  private listeners = new Map<keyof Events, Set<Listener<any>>>();

  on<K extends keyof Events>(type: K, fn: Listener<Events[K]>): () => void {
    let set = this.listeners.get(type);
    if (!set) this.listeners.set(type, (set = new Set()));
    set.add(fn);
    return () => set!.delete(fn);
  }

  emit<K extends keyof Events>(type: K, payload: Events[K]) {
    this.listeners.get(type)?.forEach(fn => fn(payload));
  }
}

// const bus = new Emitter<{ token: { text: string }; done: { usage: number } }>();
// bus.on('token', p => p.text);   // p is typed
```
Returning an unsubscribe function fits React effects: `useEffect(() => bus.on('token', handler), [])`.

---

## C11. Machine coding: accessible autocomplete (60 min)

**Checking:** debounce, cancel stale requests, cache, keyboard, ARIA combobox, loading/empty/error states.

```tsx
import { useEffect, useId, useRef, useState } from 'react';

type Props = {
  fetchSuggestions: (q: string, signal: AbortSignal) => Promise<string[]>; // must be stable (useCallback)
  onSelect: (value: string) => void;
};

export function Autocomplete({ fetchSuggestions, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const cache = useRef(new Map<string, string[]>());
  const listId = useId();

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setItems([]);
      setOpen(false);
      return;
    }
    const hit = cache.current.get(q);
    if (hit) {
      setItems(hit);
      setOpen(true);
      setActive(-1);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setStatus('loading');
      try {
        const result = await fetchSuggestions(q, ctrl.signal);
        cache.current.set(q, result);
        setItems(result);
        setOpen(true);
        setActive(-1);
        setStatus('idle');
      } catch {
        if (!ctrl.signal.aborted) setStatus('error');
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [query, fetchSuggestions]);

  const choose = (value: string) => {
    setQuery(value);
    setOpen(false);
    onSelect(value);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') return setOpen(false);
    if (!open || items.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(i => (i + 1) % items.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(i => (i <= 0 ? items.length - 1 : i - 1));
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      choose(items[active]);
    }
  };

  return (
    <div>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => setOpen(false)}
      />
      {open && (
        <ul id={listId} role="listbox">
          {items.length === 0 && <li role="option" aria-disabled="true" aria-selected={false}>No results</li>}
          {items.map((item, i) => (
            <li
              key={item}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={e => {
                e.preventDefault();
                choose(item);
              }}
            >
              {item}
            </li>
          ))}
        </ul>
      )}
      <div role="status" aria-live="polite" style={{ position: 'absolute', left: -9999 }}>
        {status === 'loading' ? 'Loading suggestions' : status === 'error' ? 'Could not load suggestions' : open ? `${items.length} suggestions` : ''}
      </div>
    </div>
  );
}
```
Known simplifications to call out yourself: `choose` sets the query, which triggers one more (cached) lookup; highlight the matched substring; the cache never expires (use C8); `onMouseDown` + `preventDefault` keeps focus in the input so `onBlur` doesn't close the list before the click lands.

---

## C12. More prompts to practise (no solution here; notes in whetstone)

| Prompt | Where |
|---|---|
| Virtualised list from scratch (fixed, then variable heights) | [whetstone/06-02](../../fe-hands-on/whetstone/06-machine-coding/02-virtualized-list-from-scratch.md) |
| Modal with focus trap | [whetstone/06-03](../../fe-hands-on/whetstone/06-machine-coding/03-modal-dialog-focus-trap.md) |
| Infinite feed with cursor pagination | [whetstone/06-06](../../fe-hands-on/whetstone/06-machine-coding/06-infinite-feed-cursor-pagination.md) |
| File uploader with concurrency + progress | [whetstone/06-08](../../fe-hands-on/whetstone/06-machine-coding/08-file-uploader-concurrency-progress.md) |
| Undo/redo (command vs snapshot) | [whetstone/06-05](../../fe-hands-on/whetstone/06-machine-coding/05-undo-redo-command-vs-snapshot.md) |
| Reactive store with Proxy | [whetstone/01-08](../../fe-hands-on/whetstone/01-javascript-internals/08-reactive-store-with-proxy.md) |
| Nested comments (recursive render, collapse, reply) | plan item, 11 Nov |
| Streaming Markdown renderer: split into closed blocks + live tail | [whetstone/14-02](../../fe-hands-on/whetstone/14-ai-frontend/02-streaming-markdown-safe-rendering.md) |
| Tool-approval card driven by a reducer (pending → awaiting → approved/rejected) | [whetstone/14-03](../../fe-hands-on/whetstone/14-ai-frontend/03-tool-calling-generative-ui-human-loop.md) |
