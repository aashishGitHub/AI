# Build a file uploader with concurrency, progress, cancel and retry
**Round:** 06 · Machine Coding · **Level:** Lead / Staff · **Time:** 35 min · **Tags:** uploads · progress · xhr
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
Multi-file uploader: drag-and-drop or picker, at most 3 concurrent, per-file progress, cancel or retry individual files, validation before any request.

Tests: drop 8 → 3 start; one finishes → next starts, never >3; progress updates only that file's bar; cancel aborts and starts next queued; retry requeues a failed file; 12 MB over a 10 MB limit rejected with no request.

## Core answer (key points)
- **Per-file state machine** as a discriminated union: `queued → uploading(loaded) → done | failed(error, attempts) | cancelled`; `failed → queued` on retry. Rejected (validation) is a terminal state too.
- **Store outside the page component** (context + reducer, or a tiny external store) so uploads survive in-app navigation.
- **Concurrency-limited queue:** FIFO of ids + `Map<id, AbortController>` for active; `pump()` starts work while `active < limit`; every completion (any outcome) frees a slot and pumps.
- **Transport:** `XMLHttpRequest` because `xhr.upload.onprogress` gives upload progress; `fetch` upload progress isn't broadly available (streaming request bodies are limited — verify current support). Abort via `xhr.abort()` wired to an AbortSignal.
- **Presigned URLs:** browser PUTs directly to object storage; API server only signs.
- **Retry policy:** only network errors and 5xx, exponential backoff with jitter; never 4xx.
- **Validation first:** size, count, type via `accept` (UX hint) + server-side magic-byte check (`accept` and `file.type` are spoofable).
- **UX/a11y:** real `<input type="file" multiple accept>` (keyboard/AT path) plus drop zone; per-file `<progress value max>` with text %; overall progress; polite announcements of completions/failures; `beforeunload` warning while active.
- **Large files:** chunk with `file.slice()`, S3 multipart (per-part presigned URLs) or tus for resumable; persist upload id + done parts to resume after reload; per-part checksums; never read whole multi-GB files into memory.

## Mental model / flow
```
drop/pick → validate → items[] (queued | rejected)
queue: [f4 f5 f6 f7 f8]   active: {f1,f2,f3}  limit 3
f2 done  → active {f1,f3} → pump → start f4
cancel f3 → abort xhr → status cancelled → pump → start f5
f1 fails (5xx, attempt<3) → backoff → retry ; (4xx) → failed
user Retry on failed → status queued → enqueue
```

## Code sketch
```ts
type Item =
  | { id: string; file: File; status: 'queued' }
  | { id: string; file: File; status: 'uploading'; loaded: number }
  | { id: string; file: File; status: 'done'; key: string }
  | { id: string; file: File; status: 'failed'; error: string; attempts: number }
  | { id: string; file: File; status: 'cancelled' }
  | { id: string; file: File; status: 'rejected'; reason: string };

export function putWithProgress(url: string, file: File, onProgress: (n: number) => void, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('aborted', 'AbortError'));
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.upload.onprogress = e => e.lengthComputable && onProgress(e.loaded);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(Object.assign(new Error(`HTTP ${xhr.status}`), { status: xhr.status })));
    xhr.onerror = () => reject(new TypeError('network'));
    xhr.onabort = () => reject(new DOMException('aborted', 'AbortError'));
    signal.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

export function createPool(limit: number, run: (id: string, signal: AbortSignal) => Promise<unknown>) {
  const waiting: string[] = [];
  const active = new Map<string, AbortController>();
  const pump = () => {
    while (active.size < limit && waiting.length) {
      const id = waiting.shift()!;
      const ac = new AbortController();
      active.set(id, ac);
      run(id, ac.signal).catch(() => {}).finally(() => { active.delete(id); pump(); });
    }
  };
  return {
    add(id: string) { waiting.push(id); pump(); },
    cancel(id: string) {
      const i = waiting.indexOf(id);
      if (i >= 0) waiting.splice(i, 1);
      active.get(id)?.abort();
    },
    get running() { return active.size; },
  };
}

export const retryable = (e: unknown) =>
  e instanceof TypeError || ((e as { status?: number }).status ?? 0) >= 500;

export function validate(f: File, maxBytes: number, types: string[]): string | null {
  if (f.size > maxBytes) return `Larger than ${Math.round(maxBytes / 1e6)} MB`;
  if (types.length && !types.some(t => t.endsWith('/*') ? f.type.startsWith(t.slice(0, -1)) : f.type === t)) return 'Unsupported type';
  return null;
}
```
`run(id, signal)` = get presigned URL → `putWithProgress` (dispatching `progress` actions, throttled to rAF) → `done`; on AbortError → `cancelled`; on retryable error with attempts left → backoff then retry; else `failed`.

UI outline: `<DropZone>` (dragover preventDefault, drop → `files`), visible `<input type=file>`, `<UploadRow>` per item (`<progress>`, status text, Cancel / Retry buttons with file name in `aria-label`), `<div role="status" aria-live="polite">` for completions.

## Trade-offs & pitfalls
- Progress events can fire hundreds of times per second; throttle store updates (rAF) and keep each row memoized by id.
- `lengthComputable` false → indeterminate progress.
- Progress reaching 100% ≠ done; server may still be processing. Show "Finalizing…".
- Drop events on `window` outside the zone navigate to the file — prevent default globally.
- Cancel of a queued (not yet active) item must remove it from `waiting`, or it'll start later.
- Presigned URL expiry vs retry/backoff time.

## Likely follow-ups
- **Why not `Promise.all` with chunks of 3?** Batches wait for the slowest; a pool refills slots immediately.
- **Resumable after reload?** Persist upload id + completed part ETags (IndexedDB); `File` handles can't be persisted, user reselects or use File System Access where available.
- **Security?** Server validates type/size/content, virus scan, scoped presigned URLs (method, key, size, expiry).
- **Testing?** Fake XHR (or MSW, which I believe supports upload progress only partially — verify), assert pool never exceeds 3 with deferred promises; validation unit tests.

## Say it in 60 seconds
Each file is an item with its own state machine — queued, uploading with bytes loaded, done, failed with attempts, cancelled, or rejected at validation — in a store that lives outside the page. Uploads go through a pool with a limit of three: a waiting queue plus a map of active abort controllers, and any completion frees a slot and starts the next. I use XHR for real upload progress and wire its abort to an AbortSignal, uploading straight to storage with presigned URLs. Retries are only for network errors and 5xx with backoff. Size and type are validated before any request, with server-side checks too. The UI keeps a real file input next to the drop zone, per-file progress elements and polite announcements, and big files go chunked and resumable.
