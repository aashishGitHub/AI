# When and how do you move work off the main thread with Web Workers?
**Round:** 07 · Browser & Web Platform · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** web workers · comlink · transferables
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: a CSV import freezes the UI for 4 s while parsing 200,000 rows and building a search index. Move it off the main thread.

## What they're really testing
Judgment on what belongs in a worker, the real cost of message passing (structured clone vs transfer), and production concerns: progress, cancel, errors, pools, bundling, tests.

## Core answer (key points)
- **Good worker work:** CPU-bound, no DOM: CSV/JSON parsing, search indexing, diffing, image processing, syntax highlighting, compression, crypto, WASM. Freeing the main thread directly improves INP and keeps input/rendering responsive.
- **Not worker work:** anything needing DOM/layout; tiny tasks where hop + serialization costs more than the work.
- **Messaging:** `postMessage` uses structured clone (deep copy; functions and DOM nodes can't be sent). Copy cost scales with payload size, so keep the protocol coarse: send the `File`/`ArrayBuffer`, not 200k row objects.
- **Transferables:** `ArrayBuffer`, `ImageBitmap`, `MessagePort`, `OffscreenCanvas` move ownership with zero copy; the sender's copy becomes detached (byteLength 0).
- **SharedArrayBuffer + Atomics:** true shared memory, but only in cross-origin isolated pages (`COOP: same-origin` + `COEP: require-corp` or `credentialless`), which can break third-party embeds.
- **For the scenario:** pass the `File` to the worker (Files are cloneable cheaply as handles), stream-parse in the worker in chunks, post progress every N rows, build the index there and keep it there; main thread sends queries, gets small results back.
- **Ergonomics:** typed request/response with ids, or **Comlink** (RPC proxy over postMessage) for `await api.query('x')`.
- **Production concerns:** cancel via `AbortController`-like message or `worker.terminate()`; propagate errors (`onerror`, `onmessageerror`, typed error replies); pool size ≈ `navigator.hardwareConcurrency - 1` for parallel jobs; bundle with `new Worker(new URL('./x.worker.ts', import.meta.url), { type: 'module' })` (Vite/webpack 5 understand this).

## Mental model / flow
```
main thread                         worker
 File picked ──postMessage(file)──►  stream parse chunks
                ◄── {progress: 25%}  ...
                ◄── {progress: 50%}  build index (kept in worker)
                ◄── {done, count}
 user types  ──{query:'acme'}─────►  search(index)
                ◄── {results: [...50 ids]}   (small payload)
```

## Code sketch
```ts
// import.worker.ts
import { parseCsvStream, buildIndex, search, type Index } from './import-core';

let index: Index | null = null;
let cancelled = false;

type Msg =
  | { type: 'import'; file: File }
  | { type: 'cancel' }
  | { type: 'query'; id: number; q: string };

self.onmessage = async ({ data }: MessageEvent<Msg>) => {
  if (data.type === 'cancel') { cancelled = true; return; }
  if (data.type === 'query') {
    self.postMessage({ type: 'result', id: data.id, hits: index ? search(index, data.q) : [] });
    return;
  }
  cancelled = false;
  try {
    const rows = [];
    for await (const batch of parseCsvStream(data.file.stream(), 5_000)) {
      if (cancelled) return self.postMessage({ type: 'cancelled' });
      rows.push(...batch);
      self.postMessage({ type: 'progress', rows: rows.length });
    }
    index = buildIndex(rows);
    self.postMessage({ type: 'done', rows: rows.length });
  } catch (err) {
    self.postMessage({ type: 'error', message: String(err) });
  }
};
```
```ts
// main
const worker = new Worker(new URL('./import.worker.ts', import.meta.url), { type: 'module' });
worker.postMessage({ type: 'import', file });

// Transfer instead of copy for raw buffers:
worker.postMessage({ type: 'raw', buf }, [buf]); // buf.byteLength === 0 afterwards
```

## Trade-offs & pitfalls
- Returning all 200k parsed rows to the main thread re-introduces a big clone and a big React render; keep data in the worker, return pages or ids, and virtualize the list.
- Worker startup costs tens of ms plus module download; create once and reuse, or prewarm on intent.
- Debugging and error stacks are harder; send structured errors and test core logic as plain functions.
- Cross-origin isolation for SharedArrayBuffer can break ads, embeds, OAuth popups; weigh carefully.
- Sometimes the right fix is less work (server-side import, pagination, virtualization) or yielding in chunks on the main thread with `scheduler.yield()` (Chromium; fallback `setTimeout`/`MessageChannel`).

## Likely follow-ups
- **Worker vs `requestIdleCallback`?** rIC still runs on the main thread in idle gaps; fine for small low-priority work. Workers actually run in parallel.
- **Share one worker across tabs?** `SharedWorker` (historically missing on some mobile browsers, verify current support) or elect a leader tab with Web Locks and fan out via BroadcastChannel.
- **How do you test it?** Keep the core pure and unit-test it directly; test the protocol with a fake worker or run real workers in Vitest browser mode / Playwright.
- **OffscreenCanvas?** Lets a worker draw charts/canvas without touching the main thread; transfer control with `canvas.transferControlToOffscreen()`.
- **WASM?** Pairs well with workers for heavy compute (parsers, image codecs, SQLite).

## Say it in 60 seconds
I move CPU-heavy, DOM-free work into a worker: parsing, indexing, diffing, image processing, WASM. That keeps the main thread free for input and rendering, which is exactly what INP measures. For the CSV import I'd hand the File to a module worker, stream-parse it in chunks, post progress messages, build the search index inside the worker and keep it there, so the main thread only sends queries and receives small result sets. postMessage deep-copies via structured clone, so I keep messages coarse and transfer ArrayBuffers instead of copying them. I add cancellation, typed error messages, and Comlink if we want RPC ergonomics. I don't use a worker for tiny tasks or anything needing the DOM, and I first check whether the real fix is doing less work, virtualization or yielding.
