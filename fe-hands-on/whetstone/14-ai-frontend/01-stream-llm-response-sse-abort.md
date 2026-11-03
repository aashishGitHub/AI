# Stream an LLM response into the UI: fetch streams, SSE parsing, abort and render batching
**Round:** 14 · AI-Powered Frontends · **Level:** Lead / Staff · **Time:** 20 min · **Tags:** llm · streaming · sse
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: chat UI where tokens stream in, the user can press Stop, and the page stays smooth on long answers.

## What they're really testing
Byte-level stream handling (chunk boundaries, UTF-8), a correct SSE parser, cancellation, render batching, and a11y for live text. Plus "keys stay on the server".

## Core answer (key points)
- **Architecture:** browser -> your backend (holds the provider key, enforces auth/rate limits) -> provider. Backend relays as Server-Sent Events.
- **Why `fetch` + stream, not `EventSource`:** `EventSource` is GET-only with no custom headers or body. Chat needs POST + JSON + auth, and `AbortController`.
- **Reading:** `response.body.getReader()`, `TextDecoder` with `{ stream: true }` so multi-byte characters split across chunks don't become U+FFFD.
- **Parsing SSE:** buffer text; events end at a blank line; one chunk may contain several events or half of one. Per line: `event:`, `data:` (multiple data lines join with `\n`), `id:`, and lines starting with `:` are comments/heartbeats. Normalize CRLF.
- **Message state machine:** `streaming -> done | stopped | error`. Keep partial text on error/stop.
- **Batching:** accumulate deltas in a buffer and flush at most once per animation frame. Avoid one React update per token.
- **Stop:** `AbortController` on the fetch; server should stop generation on client disconnect (cost).
- **UX/a11y:** don't make the streaming node an `aria-live` region token by token; announce completion once. Auto-scroll only if the user is already near the bottom. Offer "Regenerate"; never auto-retry side-effecting tool actions.

## Mental model / flow
```
fetch POST /api/chat (signal)
  -> ReadableStream<Uint8Array>
  -> TextDecoder(stream) -> string buffer
  -> split on "\n\n" -> parse fields -> {event, data}
  -> 'delta' -> pending += data -> rAF flush -> setState once per frame
  -> stream end -> status 'done' | abort -> 'stopped' | throw -> 'error'
```

## Code sketch
```ts
// Own sketch: minimal SSE async iterator (CRLF handling simplified)
export async function* sseEvents(res: Response) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) !== -1) {
        const ev = parse(buf.slice(0, i));
        buf = buf.slice(i + 2);
        if (ev) yield ev;
      }
    }
    const tail = parse((buf + decoder.decode()).trim());
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function parse(block: string) {
  let event = 'message'; const data: string[] = [];
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const c = line.indexOf(':');
    const field = c < 0 ? line : line.slice(0, c);
    const val = c < 0 ? '' : line.slice(c + 1).replace(/^ /, '');
    if (field === 'event') event = val; else if (field === 'data') data.push(val);
  }
  return data.length ? { event, data: data.join('\n') } : null;
}
```
```ts
// rAF batching inside the send loop
let pending = '', raf = 0;
const flush = () => { raf = 0; const s = pending; pending = ''; appendToAssistant(id, s); };
for await (const ev of sseEvents(res)) {
  if (ev.event === 'delta') { pending += ev.data; raf ||= requestAnimationFrame(flush); }
  if (ev.event === 'error') throw new Error(ev.data);
}
if (raf) cancelAnimationFrame(raf); flush(); setStatus(id, 'done');
```
Note: a lone `\r` split exactly at a chunk boundary needs extra care if the server emits CR-only line endings; the simplified version above ignores that.

## Trade-offs & pitfalls
- Re-parsing the whole Markdown message on every token is quadratic; batch and memoize completed blocks (see 02).
- Proxies/CDNs that buffer responses kill streaming; disable buffering and send heartbeats to keep idle connections open.
- One active stream per conversation: abort the previous before starting a new one.
- Calling the provider from the browser with a secret key leaks it. Always proxy.
- 429 handling: show a friendly message with retry time, not a raw error.

## Likely follow-ups
- **WebSockets instead?** Fine for bidirectional sessions; SSE over HTTP is simpler, works with standard auth/proxies, and one-way is all chat needs.
- **Resume after network drop?** Use event `id`s and a server-side buffer keyed by message id; client re-requests from last id. Not free; many products just offer Regenerate.
- **How do you test it?** Feed the parser hand-crafted chunk splits (mid-event, mid-emoji, CRLF), and test abort mid-stream.
- **Why rAF, not throttle?** Aligns state updates with paint; at most one render per frame regardless of token rate.

## Say it in 60 seconds
The browser calls our own backend, which holds the key and streams Server-Sent Events. I use fetch rather than EventSource because I need POST, auth headers and AbortController. I read the body with a streaming TextDecoder so characters split across chunks survive, buffer until the blank-line delimiter, parse event and data lines, and append deltas to the assistant message. Updates are batched to one per animation frame, the message has a clear streaming, done, stopped or error state, Stop aborts the fetch and the server stops generating, and partial text is kept. For accessibility I announce completion once instead of reading each token, and I only auto-scroll when the user is already at the bottom.
