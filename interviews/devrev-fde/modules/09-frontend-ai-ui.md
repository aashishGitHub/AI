# Module 09 — Frontend for AI products

> This module covers the browser side of an AI feature: streaming tokens into the UI, modelling a conversation as state, cancelling and recovering, showing evidence so users can trust the answer, keeping it accessible, keeping it fast, and testing the logic without a browser. The code is my own Agent Console UI in `AI/fe-hands-on/app/agent-console-ui/app/` (Next.js 16.3.2, React 19.2.8, `react-markdown` ^10.1.0, per its `package.json`) and the Go server it consumes in `AI/fe-hands-on/server/stream.go`. Everything in the Agent Console is lane **[L]**, my own build. The autocomplete and news-feed material in Phases 5 and 6 comes from my written design docs in `AI/interviews/frontend-system-design/`, which are paper designs and not built code. Couchbase UI work is lane **[P]** and I only reference it in prose (ticket IDs from `AI/interviews/devrev-fde/README.md`); I did not open that code for this module.

## Phases at a glance

| Phase | Purpose | Main code |
|---|---|---|
| 1. Streaming fundamentals | Pick the transport and own the wire contract (`sources`, `token`, `done`, `error`). | `app/lib/chat.ts`, `server/stream.go` |
| 2. State design | Model a streaming conversation as a pure reducer with a status enum. | `app/lib/reducer.ts` |
| 3. Abort, errors and reconnection | Cancel cleanly, surface failures in-band, and know exactly what is not recovered. | `app/page.tsx`, `app/lib/chat.ts` |
| 4. Trust UX | Show evidence before the answer, render Markdown safely, handle refusals honestly. | `app/page.tsx`, `server/stream.go` |
| 5. Accessibility and keyboard | What the console does, and the combobox pattern from my autocomplete design. | `app/page.tsx`, `autocomplete.md` |
| 6. Performance | Debounce vs throttle, caching, virtualization, cursor pagination, token flood. | `next-js-app/lib/utils.ts`, `news-feed.md` |
| 7. Testing UI logic | Reducer tests and a fake byte stream, with the untested seams named. | `app/lib/*.test.ts` |

---

## Phase 1 — Streaming fundamentals (SSE vs WebSocket vs polling, the event contract)

### 🟢 Beginner

**Q:** What is streaming in an AI UI, and why not just wait for the full answer?

**A:** Streaming means the server sends the answer in small pieces as the model produces them, and the browser paints each piece immediately. I do it because time to first token is what the user feels. My own note recorded a real local run where a short turn finished in 154 ms and a 46-token turn in 1680 ms, so a user who waits for the whole body stares at nothing for up to that long. With streaming the first words appear almost at once and the user can start reading or stop the answer early.

**Q:** SSE, WebSocket or polling for token streaming?

**A:** For token streaming I pick Server-Sent Events, which is one-way server-to-client over ordinary HTTP. My note 02 gives the reasoning: WebSocket buys bidirectional frames I do not need and adds a second protocol to run and proxy. Polling would add latency equal to the poll interval and wasteful requests, so it suits status checks, not live text. I would pick WebSocket only if the client genuinely needs to push frequent messages on the same connection, for example live collaboration.

**Q:** In what order do the events arrive, and what ends a turn?

**A:** The server sends one `sources` event when retrieval is enabled, then a stream of `token` events, and then exactly one terminator, which is either `done` or `error`. The `done` event carries the usage numbers, so the UI can show prompt tokens, completion tokens and latency for that turn. If retrieval fails, the server sends an `error` event and no tokens, and if the client disconnects the server sends nothing at all. So the UI can rely on a terminator in normal operation, but I should not assume one in every failure, which I come back to in Phase 3.

### 🟡 Intermediate

**Q:** What is the event contract between your server and your UI?

**A:** The contract is four JSON event types: `sources`, `token`, `done` and `error`. The TypeScript type on the client is a discriminated union that mirrors the Go struct, so the UI never knows which model produced the text. That is why I could swap providers behind a Go interface without touching the frontend, which is what note 02 calls the swap seam. The reducer's `Action` type even includes the stream events directly, so there is no translation layer between transport and state.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:19-24`

```ts
/** Mirrors streamEvent in server/stream.go. */
export type StreamEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; value: string }
  | { type: "done"; usage?: Usage }
  | { type: "error"; value: string };
```

**Source:** `AI/fe-hands-on/server/stream.go:18-23`

```go
type streamEvent struct {
	Type    string   `json:"type"`              // "sources" | "token" | "done" | "error"
	Value   string   `json:"value,omitempty"`   // token text, or error message
	Sources []Source `json:"sources,omitempty"` // only on the "sources" frame
	Usage   *usage   `json:"usage,omitempty"`   // only on the "done" frame
}
```

I would point at the comment on the Go struct and the matching comment on the TypeScript type: the contract has one definition on each side and the types are the only coupling.

**Q:** Why did you use `fetch` with a `ReadableStream` instead of `EventSource`?

**A:** `EventSource` can only issue a GET with no body, so multi-turn history would have to be squeezed into the URL, and I could not cancel it as cleanly as an `AbortController`-driven fetch. My note 02 predicted exactly this: the single-shot version used `?q=`, and multi-turn history forces POST plus `fetch` plus `ReadableStream`. The cost is a few extra lines to parse SSE framing myself and no built-in auto-reconnect. I accept that cost because history and cancellation are the two things the console needs most.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:86-108`

```ts
export async function* streamChat(
  messages: Message[],
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (!response.ok) {
    // 4xx/5xx come back as plain text, not SSE — surface the server's reason
    // rather than a generic failure.
    const detail = (await response.text()).trim();
    throw new Error(detail || `request failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("response had no body to stream");
  }

  yield* parseSSE(response.body, signal);
}
```

For this snippet I talk about the two failure paths: a non-OK status arrives as plain text and becomes an `Error` with the server's reason, and an OK status hands the body to the parser. The 4xx and 5xx text is plain, not SSE, because the server rejects bad input before it ever writes the event-stream headers.

**Q:** Walk me through how the parser turns bytes into events.

**A:** I read chunks from the reader, decode them with a streaming `TextDecoder`, append to a string buffer, and only emit an event when I see the blank-line terminator. A network chunk is not an event: one read can hold half an event or three of them. The `{ stream: true }` option keeps a multi-byte character that is split across two reads from being corrupted. A malformed JSON frame is skipped so one bad frame does not kill an otherwise healthy answer.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:49-71`

```ts
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);

        if (!block.startsWith("data: ")) continue;
        try {
          yield JSON.parse(block.slice(6)) as StreamEvent;
        } catch {
          // A malformed frame should not kill an otherwise healthy stream.
          continue;
        }
      }

      if (signal?.aborted) break;
    }
```

I would say out loud that the tests for this behaviour feed the parser chunks cut at awkward points, because that is the bug that only appears under load.

**Q:** What does the server have to do for streaming to actually work?

**A:** It has to set the event-stream content type, turn off caching, tell proxies not to buffer, and flush after every event. In my Go handler the explicit flush matters most: without it the bytes sit in Go's buffer until the handler returns, which would defeat streaming entirely. The `X-Accel-Buffering: no` header is there to stop a reverse proxy from buffering the stream; I have only tested locally, so I have not proven it against a real proxy. The frontend lesson is that a streaming bug that shows up as one big lump of text is often a buffering layer in between, not a parser bug.

**Source:** `AI/fe-hands-on/server/stream.go:134-147`

```go
func writeEvent(w http.ResponseWriter, flusher http.Flusher, event streamEvent) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	// SSE framing: "data: <payload>\n\n"; the blank line terminates the event.
	if _, err := fmt.Fprintf(w, "data: %s\n\n", payload); err != nil {
		return err
	}
	// Without an explicit flush the bytes sit in Go's buffer until the handler
	// returns, which would defeat streaming entirely.
	flusher.Flush()
	return nil
}
```

I would use this snippet to show that the frame format `data: <payload>` plus a blank line is written in exactly one place on the server and parsed in exactly one place on the client.

### 🔴 Senior

**Q:** Where does your SSE parser stop being correct, and what would you change before putting it in front of a customer?

**A:** The parser handles exactly the dialect my own server emits, which is single-line `data: <json>` frames separated by `\n\n`, and I have not made it a general SSE parser. It does not handle `\r\n` line endings, multi-line `data:` fields, or the `event:`, `id:` and `retry:` fields. That is fine while I own both ends, but it would be a risk behind a proxy or with a third-party stream that normalises line endings. The trade-off is simplicity and a fully tested small parser versus spec completeness. The failure mode is silent: a CRLF stream would never find a `\n\n` boundary, buffer forever, and the UI would sit on "Searching the documentation" with no error. I have not measured this against any real proxy, and I have not tested CRLF input against the real parser.

**Illustrative (not from the repo):**

```ts
export function nextFrame(buffer: string): { frame: string; rest: string } | null {
  const match = /\r?\n\r?\n/.exec(buffer);
  if (!match) return null;
  return {
    frame: buffer.slice(0, match.index),
    rest: buffer.slice(match.index + match[0].length),
  };
}
```

If I hardened the parser I would swap `indexOf("\n\n")` for a boundary finder like this one, add tests for CRLF and for `: keep-alive` comment frames, and still treat everything the server does not send as out of scope. I checked in the scratchpad that it handles CRLF, LF and a partial buffer.

**Follow-up they will ask:** Why does the server report a mid-stream failure as an `error` event instead of an HTTP status code?

**A:** Once the server has written the 200 status and the event-stream headers, it cannot change the status, and tokens already flushed cannot be retracted. So the only honest channel is an in-band `error` event, which my note 02 lists as the cost of streaming over buffering. In `stream.go` the headers are written before retrieval runs, which means even a retrieval failure arrives as a 200 response carrying an `error` event. Only validation failures, which happen before the headers, come back as real 4xx plain text.

**Source:** `AI/fe-hands-on/server/stream.go:177-188`

```go
	// Bound the whole generation. Without this a wedged upstream holds the
	// connection, and its goroutine, indefinitely.
	ctx, cancel := context.WithTimeout(r.Context(), s.cfg.RequestTimeout)
	defer cancel()

	question := req.Messages[len(req.Messages)-1].Content
	log := s.log.With("question_chars", len(question), "turns", len(req.Messages))

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no") // stop proxies buffering the stream
	w.WriteHeader(http.StatusOK)
```

**Source:** `AI/fe-hands-on/server/stream.go:216-232`

```go
	// --- generate -----------------------------------------------------------
	emit := func(token string) error {
		return writeEvent(w, flusher, streamEvent{Type: "token", Value: token})
	}

	u, err := s.provider.Stream(ctx, buildMessages(chunks, req.Messages), emit)
	if err != nil {
		// A cancelled context means the client hung up; there is nobody left to
		// send an error frame to, so just record it.
		if r.Context().Err() != nil {
			log.Info("client disconnected", "err", err)
			return
		}
		log.Error("generation failed", "err", err)
		writeEvent(w, flusher, streamEvent{Type: "error", Value: err.Error()})
		return
	}
```

I would add that a client disconnect sends no frame at all, because nobody is listening, which matters for the failure case in Phase 3.

**Q:** When is streaming the wrong choice?

**A:** Streaming costs me error-handling complexity, so I would not use it when the answer is short, when the user cannot act on partial output, or when the downstream consumer needs the complete result, for example a structured JSON payload that is useless until it is whole. Note 02 states the cost directly: once 200 tokens are flushed they cannot be retracted, so failures must be in-band. A second cost is the UI work in this module: abort, partial state and the terminator problem all exist only because of streaming. I have not measured a case where buffering would have been better, so this is a design trade-off and not a benchmark.

---

## Phase 2 — State design (a pure reducer for a streaming conversation)

### 🟢 Beginner

**Q:** Why model the conversation with a reducer instead of several `useState` calls?

**A:** A reducer is a plain function from the current state and an action to the next state, so all the rules live in one place. Every stream event and every user gesture becomes an action, which means the component only dispatches and renders. It also means I can test the rules with ordinary function calls and no DOM. My GFE guide makes the same point about replacing several booleans with a single `status` enum, because booleans allow contradictory states and an enum cannot.

### 🟡 Intermediate

**Q:** Which values do you store and which do you derive?

**A:** I store the minimal facts: the status enum and the list of turns. Anything computable from those, I derive at render time instead of syncing it with an effect, which is the rule from my GFE state-design notes. In the page, `streaming` is just a comparison on `state.status`, and the per-turn streaming flag is that value combined with "is this the last turn". The advantage is that there is no second source of truth that can drift out of step with the reducer.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:72-72`

```tsx
  const streaming = state.status === "streaming";
```

**Q:** Walk me through your state shape and reducer.

**A:** The state is a `status` of `"idle"` or `"streaming"` plus an array of turns, and each turn holds the question, the answer so far, the sources, optional usage, an optional error and an optional aborted flag. The `Action` type is the union of `ask`, `abort`, `retry` and the four stream events, so the stream feeds the reducer directly with no translation layer. A helper called `updateLast` copies the array and replaces only the final turn, because every streaming update targets the open turn. Nothing is mutated, so React sees new references and re-renders.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:9-29`

```ts
export type Turn = {
  question: string;
  answer: string;
  sources: Source[];
  usage?: Usage;
  error?: string;
  aborted?: boolean;
};

export type State = {
  status: "idle" | "streaming";
  turns: Turn[];
};

export type Action =
  | { type: "ask"; question: string }
  | { type: "abort" }
  | { type: "retry" }
  | StreamEvent;

export const initialState: State = { status: "idle", turns: [] };
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:40-62`

```ts
export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ask":
      return {
        status: "streaming",
        turns: [...state.turns, { question: action.question, answer: "", sources: [] }],
      };

    case "retry": {
      // Drop the failed turn and re-ask it, so a transient failure doesn't
      // leave a dead entry in the transcript.
      const last = state.turns[state.turns.length - 1];
      if (!last) return state;
      return {
        status: "streaming",
        turns: [...state.turns.slice(0, -1), { question: last.question, answer: "", sources: [] }],
      };
    }

    // Citations arrive before the first token so evidence is visible while the
    // answer is still being written.
    case "sources":
      return updateLast(state, { sources: action.sources });
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:64-83`

```ts
    case "token":
      return updateLast(state, {
        answer: (state.turns[state.turns.length - 1]?.answer ?? "") + action.value,
      });

    case "done":
      return { ...updateLast(state, { usage: action.usage }), status: "idle" };

    case "error":
      return { ...updateLast(state, { error: action.value }), status: "idle" };

    case "abort":
      // Keep whatever text already arrived: a half-answer the user stopped is
      // still worth reading, and deleting it would feel like a crash.
      return { ...updateLast(state, { aborted: true }), status: "idle" };

    default:
      return state;
  }
}
```

I would point at three decisions here: `done`, `error` and `abort` each return the status to idle, `abort` and `error` keep the partial answer, and `retry` replaces the failed turn instead of appending a dead entry.

**Q:** What does `toMessages` do and why does it exist?

**A:** It builds the request history from the stored turns, and it deliberately leaves out any turn that errored, was aborted, or has an empty answer. It also never sends the last turn's answer, because that turn is the one currently being written. If I replayed a half-answer to the model as if it were real assistant output, the next turn's context would be poisoned. This is separate from the display state on purpose: what the user sees and what the model is told are different projections of the same turns.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:92-105`

```ts
export function toMessages(turns: Turn[]): { role: "user" | "assistant"; content: string }[] {
  const messages: { role: "user" | "assistant"; content: string }[] = [];

  turns.forEach((turn, i) => {
    const isLast = i === turns.length - 1;
    messages.push({ role: "user", content: turn.question });

    if (!isLast && !turn.error && !turn.aborted && turn.answer.trim() !== "") {
      messages.push({ role: "assistant", content: turn.answer });
    }
  });

  return messages;
}
```

I would mention that the server independently caps history at 40 messages and 8000 characters per message in `Validate`, so the client logic is a correctness measure and not the security boundary.

**Q:** How do you test the retry rule?

**A:** I fold a short action sequence into a failed state, apply `retry`, and assert on the result. The test checks that the transcript still has one turn, that the question is preserved, that the answer and error are cleared, and that status is streaming again. The point of the first assertion is the design rule: a transient failure must not leave a dead entry in the transcript. The test needs no component and no stream, because retry is a reducer action and the network call is made separately in the page.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts:69-78`

```ts
test("retry replaces the failed turn rather than appending one", () => {
  const failed = run([askHello, { type: "error", value: "boom" }]);
  const state = reducer(failed, { type: "retry" });

  assert.equal(state.turns.length, 1, "no dead entry left in the transcript");
  assert.equal(state.turns[0].question, "hello?");
  assert.equal(state.turns[0].answer, "");
  assert.equal(state.turns[0].error, undefined);
  assert.equal(state.status, "streaming");
});
```

I would say that each assertion message or test name states the product rule, which makes the file read as a specification.

### 🔴 Senior

**Q:** What invariants should this reducer enforce, and does yours?

**A:** The invariants are that a turn ends exactly once, that stream events only apply while a turn is open, and that an aborted turn keeps its partial text. My reducer enforces the first and third through the status transitions and tests, but it does not enforce the second: a late `token` arriving after `abort` would still append to the last turn, because the `token` case never looks at `status`. Today that cannot happen in practice, because dispatches from one chunk run in a microtask chain before any click handler, and the abort rejects the next read. I reasoned that from the code and have not reproduced a late token, so treat it as an argument, not a measurement. Making the reducer defend itself is cheap, and the trade-off is one more branch against not depending on transport timing.

**Illustrative (not from the repo):**

```ts
import { reducer, type Action, type State } from "./reducer.ts";

export function strictReducer(state: State, action: Action): State {
  const fromStream =
    action.type === "sources" || action.type === "token" || action.type === "done" || action.type === "error";
  if (fromStream && state.status !== "streaming") return state;
  return reducer(state, action);
}
```

The wrapper keeps the existing reducer untouched and drops stream events when the status is idle, which I checked with a small test in the scratchpad: a token after abort is ignored by the wrapper and appended by the current reducer.

**Follow-up they will ask:** What else is fragile in the way turns are stored and rendered?

**A:** Turns are identified only by array position, and `page.tsx` renders them with `key={i}`, which is safe for an append-only list but would break if I ever inserted, deleted or reordered turns. The `retry` action also finds "the failed turn" by taking the last element, which assumes only the last turn can fail. Both assumptions hold today because the input is disabled while streaming, so there is never more than one open turn. If I allowed concurrent questions I would give each turn an id, route events by id, and replace the single `status` with per-turn status.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:92-94`

```tsx
        {state.turns.map((turn, i) => (
          <TurnView key={i} turn={turn} streaming={streaming && i === state.turns.length - 1} onRetry={retry} />
        ))}
```

---

## Phase 3 — Abort, errors and reconnection

### 🟢 Beginner

**Q:** What happens when the user clicks Stop?

**A:** The click handler calls `abort()` on the `AbortController` that was passed to `fetch`, and it dispatches an `abort` action so the UI updates immediately. The browser cancels the request, and my server's request context is cancelled when the client goes away, so the model stops generating. The partial answer stays on screen with a "Stopped." label. I keep it because deleting text the user was already reading would feel like a crash.

### 🟡 Intermediate

**Q:** Show me the control flow for a turn, including abort and errors.

**A:** `ask` dispatches the `ask` action, then `run` creates an `AbortController`, stores it in a ref, and iterates the stream with `for await`, dispatching each event. If something throws, the `catch` checks `controller.signal.aborted`: an abort is a user action that the reducer already recorded, so it must not overwrite that with an error banner. Any other failure becomes an `error` action with the message. The `finally` clears the ref only if it still points at this controller, which protects against clearing a newer request's controller.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:26-45`

```tsx
  const run = useCallback(async (messages: ReturnType<typeof toMessages>) => {
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamChat(messages, controller.signal)) {
        dispatch(event);
      }
    } catch (err) {
      // An abort is a user action, not a failure — the reducer already
      // recorded it, so don't overwrite that with an error banner.
      if (controller.signal.aborted) return;
      dispatch({
        type: "error",
        value: err instanceof Error ? err.message : "the stream failed",
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:59-62`

```tsx
  function stop() {
    abortRef.current?.abort();
    dispatch({ type: "abort" });
  }
```

I would also mention the unmount cleanup at the top of the component, which aborts any in-flight request so leaving the page stops the model generating rather than leaking the stream.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:16-24`

```tsx
  // Abort any in-flight request when the component goes away, so navigating
  // off the page stops the model generating rather than leaking the stream.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Follow the answer as it streams. `block: "end"` avoids yanking the whole
  // page when the transcript is short.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns, state.status]);
```

**Q:** How do `ask` and `retry` build the request, and why is that separate from the reducer?

**A:** The component dispatches the action first so the UI updates at once, then starts the network call with a history built by `toMessages` from the turns it currently has. For retry it builds the history from every turn except the failed one and appends that turn's question again. The reducer stays pure because it only describes state changes, and the side effect of calling the server lives in the component. One honest caveat: both functions read `state.turns` from the render closure, which is correct here because the input is disabled while streaming, but I would re-check that if concurrent turns were allowed.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:47-57`

```tsx
  function ask(question: string) {
    dispatch({ type: "ask", question });
    void run([...toMessages(state.turns), { role: "user", content: question }]);
  }

  function retry() {
    const last = state.turns[state.turns.length - 1];
    if (!last) return;
    dispatch({ type: "retry" });
    void run([...toMessages(state.turns.slice(0, -1)), { role: "user", content: last.question }]);
  }
```

**Q:** How do you distinguish a failed request from a failed stream?

**A:** A failed request is a non-OK HTTP status, which `streamChat` turns into a thrown `Error` carrying the server's plain-text reason, and the `catch` in `run` dispatches it as an `error` action. A failed stream is an in-band `error` event, which flows through the same reducer case. Both end up as `turn.error` with a Retry button, so the user sees one consistent recovery path. The retry button re-asks the same question through a reducer action that replaces the failed turn.

### 🔴 Senior

**Q:** Your console has Retry. Does it have reconnection?

**A:** No, and I want to be exact about that: it has a manual Retry that re-sends the whole question, and it has no automatic reconnect, no backoff and no resume. There is also a real gap I found by reading the code: if the connection closes cleanly without a `done` or `error` event, `parseSSE` simply finishes, `run` falls out of its loop without dispatching anything, and the reducer's status stays `"streaming"`. The input would stay disabled until the page reloads. A hard network drop is better, because the read rejects and `run` dispatches an error. I have not reproduced the clean-close case against the real server; the server code always writes `done` or `error` unless the client is gone, so I expect it only under proxy or crash conditions.

**Illustrative (not from the repo):**

```ts
import type { StreamEvent } from "./chat.ts";

export async function* withTerminalGuard(
  events: AsyncIterable<StreamEvent>,
): AsyncGenerator<StreamEvent> {
  let terminated = false;
  for await (const event of events) {
    if (event.type === "done" || event.type === "error") terminated = true;
    yield event;
  }
  if (!terminated) {
    yield { type: "error", value: "the connection closed before the answer finished" };
  }
}
```

This wrapper turns "the stream ended without a terminator" into an explicit `error` event, and I verified in the scratchpad that it passes real terminators through untouched and adds the error only when none arrived.

**Follow-up they will ask:** Would you add automatic retry, and could you resume a half-finished answer?

**A:** I would add automatic retry only before the first event arrives, because at that point nothing has been shown and re-sending is safe. After tokens have been painted, a blind retry would duplicate or contradict text, so I would stop and show Retry. Resuming mid-answer needs server support: event ids, a replay buffer and a way to continue generation, and I have not built any of that. I am not certain of the exact `EventSource` reconnect and `Last-Event-ID` semantics, so verify them in the MDN docs before claiming them; my note 02 only says `EventSource` auto-reconnects, and I deliberately gave that up by using `fetch`.

**Illustrative (not from the repo):**

```ts
import type { StreamEvent } from "./chat.ts";

export async function* retryBeforeFirstEvent(
  open: () => AsyncIterable<StreamEvent>,
  maxAttempts: number,
  backoffMs: (attempt: number) => number,
  sleep: (ms: number) => Promise<void>,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  for (let attempt = 1; ; attempt++) {
    let received = false;
    try {
      for await (const event of open()) {
        received = true;
        yield event;
      }
      return;
    } catch (err) {
      if (signal.aborted || received || attempt >= maxAttempts) throw err;
      await sleep(backoffMs(attempt));
    }
  }
}
```

The `received` flag is the whole idea: it makes the retry safe from the user's point of view, and I tested it with an injected `sleep` so the backoff values are asserted without waiting.

---

## Phase 4 — Trust UX (citations before tokens, markdown rendering, refusals)

### 🟢 Beginner

**Q:** Why show sources before the answer text?

**A:** A user who can see the evidence while the answer is still being written can judge it instead of just trusting it. The server sends a `sources` event after retrieval and before any token, and the reducer stores it on the turn. My server comment says this explicitly: the point is to let a user judge the answer against its evidence. The honest limit is that sources show what the model was given, not that the answer actually used them correctly.

**Q:** Why does the UI render Markdown instead of plain text?

**A:** The model writes Markdown: fenced code, lists and tables. Rendering that as plain text made every code block unreadable, which is the reason the code comment gives for adding the renderer. For a documentation assistant the code blocks are the product, so readable code is a trust feature as well as polish. The cost is a new dependency and the safety question of rendering model output, which I address a few questions later.

### 🟡 Intermediate

**Q:** How are citations rendered in your UI?

**A:** The sources render in a native `<details>` element above the answer, with a summary line that says how many sources the answer is grounded in. Each item is numbered `[1]`, `[2]` so it matches the `[n]` markers the server's prompt tells the model to use. I should be precise: the numbers match by convention, but the `[n]` text inside the answer is rendered as plain Markdown text and is not a clickable link to a source. The `<details>` element is closed by default, so the evidence is available but not forced on the reader.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:202-223`

```tsx
function Sources({ sources }: { sources: Source[] }) {
  return (
    <details className="rounded-lg border border-zinc-200 bg-white text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {sources.length} source{sources.length === 1 ? "" : "s"} — the answer is grounded in these
      </summary>
      <ol className="space-y-2 border-t border-zinc-200 px-3 py-2 dark:border-zinc-800">
        {sources.map((source, i) => (
          <li key={source.id} className="text-xs">
            {/* Numbered to match the [n] citations the model is told to use. */}
            <span className="font-mono text-zinc-500">[{i + 1}]</span>{" "}
            <span className="font-medium">{source.title}</span>{" "}
            <span className="text-zinc-500">({source.docId})</span>
            <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
              {source.text}
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}
```

I would say the `<details>` choice gives keyboard and screen-reader behaviour for free, and that the missing link between `[n]` and its source is the first thing I would build next.

**Q:** How do the `[n]` numbers get matched between the server and the UI?

**A:** On the server, `buildMessages` numbers each retrieved chunk `[1]`, `[2]` in the system prompt, and the prompt tells the model to cite sources by those numbers. The `sources` event carries the same chunks in the same order, and the UI numbers them by array index plus one. So the contract is positional: if the server ever reordered or filtered one list but not the other, the numbers would silently point at the wrong source. I have not written a test that locks that ordering across the two sides.

**Source:** `AI/fe-hands-on/server/stream.go:104-119`

```go
func buildMessages(chunks []Chunk, history []Message) []Message {
	var system string
	if len(chunks) == 0 {
		system = ungroundedSystemPrompt
	} else {
		var b strings.Builder
		for i, c := range chunks {
			// Numbered so the model can cite [1], [2] and the UI can match them
			// back to the sources frame.
			fmt.Fprintf(&b, "[%d] %s (%s)\n%s\n\n", i+1, c.Title, c.DocID, c.Text)
		}
		system = fmt.Sprintf(groundedSystemPrompt, strings.TrimSpace(b.String()))
	}

	return append([]Message{{Role: "system", Content: system}}, history...)
}
```

**Q:** How do you render the model's Markdown safely?

**A:** I use `react-markdown` with the `remark-gfm` plugin for tables and fenced code. The code comment claims `react-markdown` does not pass raw HTML through, so model output cannot inject markup. I did not add `rehype-raw`, which is the plugin that would change that. I have not audited link handling or confirmed the claim against the current `react-markdown` docs, so I would verify that before presenting it as a security guarantee.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:157-162`

```tsx
      <div className="rounded-2xl bg-white p-4 dark:bg-zinc-900">
        {turn.answer === "" && streaming ? (
          <p className="text-sm text-zinc-500" role="status">
            Searching the documentation…
          </p>
        ) : (
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:167-172`

```tsx
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer}</ReactMarkdown>
            {streaming && (
              <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-current align-middle" />
            )}
          </div>
        )}
```

I would talk about this as "the answer is data, rendered through a safe component" and note that the pulsing cursor span is the only streaming affordance besides the status text.

**Q:** What does the UI do when the model refuses?

**A:** Nothing special, and I should say that plainly. The server prompt tells the model to reply with the exact sentence "The provided documentation does not cover this." when the context lacks the answer, and the UI renders that sentence as ordinary Markdown. There is no refusal component, no styling and no suggestion to rephrase. The prompt's exact wording is a contract that I could match on, but matching model output by string is brittle.

**Source:** `AI/fe-hands-on/server/stream.go:86-95`

```go
const groundedSystemPrompt = `You are a documentation assistant. Answer using ONLY the context below.

Rules:
- If the context does not contain the answer, reply exactly: "The provided documentation does not cover this."
- Never invent syntax, commands, parameters, or steps that do not appear in the context.
- Cite the sources you used by their [n] number.
- Be concise and give actionable steps.

Context:
%s`
```

### 🔴 Senior

**Q:** What would you add so the UI is honest about answers that cite things that are not there?

**A:** I would validate citations on the client after the turn ends: extract every `[n]` from the answer and check that `n` is between 1 and the number of sources. An out-of-range number is a concrete, cheap signal of a bad answer, and it should render as a visible warning, not be silently shown. I would also treat the exact refusal sentence as a first-class state with its own layout, since a refusal that looks like a normal answer teaches users to ignore it. The boundary is important: this only catches malformed citations. It cannot tell whether a correct-looking `[2]` actually supports the claim, which is an evaluation problem, not a UI problem, and my eval harness is where that belongs. I have not built either check in the console.

**Illustrative (not from the repo):**

```ts
export const REFUSAL = "The provided documentation does not cover this.";

export function isRefusal(answer: string): boolean {
  return answer.trim() === REFUSAL;
}

export function checkCitations(answer: string, sourceCount: number) {
  const cited = new Set<number>();
  const invalid = new Set<number>();
  for (const m of answer.matchAll(/\[(\d+)\]/g)) {
    const n = Number(m[1]);
    (n >= 1 && n <= sourceCount ? cited : invalid).add(n);
  }
  return { cited: [...cited].sort((a, b) => a - b), invalid: [...invalid].sort((a, b) => a - b) };
}
```

Both functions are pure, so I would unit-test them like the reducer, and I would say the string match on the refusal is a deliberate coupling to the server prompt that should be replaced by a structured `refusal` flag if the contract can change.

**Follow-up they will ask:** Why is it acceptable that sources are shown before the answer, if the model might ignore them?

**A:** It is acceptable because the UI's claim is only "this is what the model was given", and the summary text says "the answer is grounded in these". That wording is slightly stronger than what I can prove, and I would soften it if a customer relied on it. The ordering still helps, because retrieval failures are explicit: in `stream.go` a retrieval error produces an `error` event and never falls back to an ungrounded answer, which the server comment calls the confident-hallucination path.

---

## Phase 5 — Accessibility and keyboard interaction (autocomplete combobox pattern)

### 🟢 Beginner

**Q:** What accessibility basics does your console already have?

**A:** The question input has a real `<label>` that is visually hidden with `sr-only`, the Send and Stop controls are real `<button>` elements, and the "Searching the documentation" message has `role="status"`. The sources use a native `<details>` and `<summary>`, which are keyboard operable without extra code. I have not run an automated audit or tested with a screen reader, so I would not claim it is accessible, only that it uses semantic elements.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:104-115`

```tsx
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the documentation…"
            autoComplete="off"
            disabled={streaming}
            className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2 outline-none focus:border-zinc-500 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
          />
```

### 🟡 Intermediate

**Q:** Why are Send and Stop two different buttons?

**A:** Stop is only reachable while streaming, which is the only time it means anything, and it aborts the request instead of just hiding the output. Send is the form's submit button and is disabled when the input is empty. Both are real `button` elements, so they are reachable and operable from the keyboard without extra work. The submit handler also refuses to run while streaming, so a second question cannot start while a turn is open.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:116-135`

```tsx
          {streaming ? (
            // Stop is only reachable while streaming, which is the only time
            // it means anything — and it aborts the request rather than just
            // hiding the output.
            <button
              type="button"
              onClick={stop}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={input.trim() === ""}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Send
            </button>
          )}
```

I would mention the weak spot honestly: the two buttons swap in the same place, and I have not checked what happens to keyboard focus when the Send button is replaced by Stop.

**Q:** What is the ARIA pattern for an autocomplete, and what does the keyboard do?

**A:** My autocomplete design doc describes a `combobox` input that controls a `listbox` of `option` items. The arrow keys move a highlighted option, Enter selects it, and Escape closes the list without selecting. The key detail from my doc is that the highlight is tracked with `aria-activedescendant`, so real focus stays in the input and typing is never interrupted. The input also carries `aria-expanded`, `aria-controls` and `aria-autocomplete="list"`, and a polite live region announces the result count. The ARIA details come from my own design doc, so verify them against the current WAI-ARIA Authoring Practices before quoting them as spec.

**Illustrative (not from the repo):**

```ts
export type ComboState = { open: boolean; active: number };
export type ComboAction =
  | { type: "open" }
  | { type: "close" }
  | { type: "move"; delta: 1 | -1; count: number }
  | { type: "reset" };

export function comboReducer(state: ComboState, action: ComboAction): ComboState {
  switch (action.type) {
    case "open":
      return { ...state, open: true };
    case "close":
      return { open: false, active: -1 };
    case "reset":
      return { ...state, active: -1 };
    case "move": {
      if (action.count === 0) return state;
      const next = (state.active + action.delta + action.count) % action.count;
      return { open: true, active: state.active === -1 && action.delta === -1 ? action.count - 1 : next };
    }
  }
}
```

**Illustrative (not from the repo):**

```tsx
import { useId, useReducer, useState } from "react";
import { comboReducer } from "./comboReducer.ts";

export function Combobox({ options, onSelect }: { options: string[]; onSelect: (v: string) => void }) {
  const [value, setValue] = useState("");
  const [state, dispatch] = useReducer(comboReducer, { open: false, active: -1 });
  const listId = useId();
  const optionId = (i: number) => `${listId}-opt-${i}`;
  const expanded = state.open && options.length > 0;

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      dispatch({ type: "move", delta: 1, count: options.length });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      dispatch({ type: "move", delta: -1, count: options.length });
    } else if (e.key === "Enter" && expanded && state.active >= 0) {
      e.preventDefault();
      onSelect(options[state.active]);
      dispatch({ type: "close" });
    } else if (e.key === "Escape") {
      dispatch({ type: "close" });
    }
  }

  return (
    <div>
      <input
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded && state.active >= 0 ? optionId(state.active) : undefined}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          dispatch({ type: "open" });
          dispatch({ type: "reset" });
        }}
        onKeyDown={onKeyDown}
      />
      <ul id={listId} role="listbox" hidden={!expanded}>
        {options.map((o, i) => (
          <li key={o} id={optionId(i)} role="option" aria-selected={i === state.active}>
            {o}
          </li>
        ))}
      </ul>
      <div aria-live="polite" className="sr-only">
        {expanded ? `${options.length} results available` : ""}
      </div>
    </div>
  );
}
```

This is not in the Agent Console; I wrote it to check that my design doc type-checks, and I tested the pure reducer, not the component in a browser. I would explain it as keeping the keyboard logic in a pure reducer and the ARIA attributes as a thin projection of that state.

**Q:** Why `aria-activedescendant` instead of moving focus to each option?

**A:** Moving DOM focus to the options would pull focus out of the input, so the caret and any input-method composition state would be lost on every arrow press. With `aria-activedescendant`, focus stays on the input and the attribute tells assistive technology which option is current. My design doc names this as the detail that separates people who built it from people who are guessing. The cost is that I must keep ids unique and in sync, which is why the sketch uses `useId`.

### 🔴 Senior

**Q:** How would you make a streaming answer accessible, and what are the trade-offs?

**A:** I would not put the whole streaming answer in an `aria-live` region, because announcing every token would be unusable for a screen-reader user. My judgment is to announce a short status when the answer starts, such as the existing "Searching" status, and a short "answer complete" message on `done`, and leave the text to be read normally. I have not tested this with a screen reader, so treat it as a hypothesis. I also see real gaps in the current code: the input is disabled while streaming, which can drop keyboard focus, and nothing restores focus after the turn ends. The trade-off is announcement noise versus the user not knowing anything happened.

**Follow-up they will ask:** What about auto-scroll?

**A:** My console scrolls to the bottom in an effect that depends on `state.turns` and `state.status`, so it runs on every token with smooth behaviour, and it will pull the user back down if they scrolled up to re-read. The `block: "end"` option avoids yanking a short page, but it does not respect the user's scroll position. My news-feed design doc states the principle: never mutate what is in the viewport without user consent. The fix is to auto-follow only while the user is already near the bottom, and show a "jump to latest" control otherwise.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:20-24`

```tsx
  // Follow the answer as it streams. `block: "end"` avoids yanking the whole
  // page when the transcript is short.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns, state.status]);
```

**Q:** How would you test the combobox?

**A:** I would test in two layers. The keyboard logic is a pure reducer, so I test it like the conversation reducer: apply moves and assert on the active index, including wrap-around and close. For the ARIA wiring I would render the component and query by role and attribute with Testing Library, which my design doc recommends over querying implementation details. I ran reducer tests for my sketch in the scratchpad, but I have not run a component test or tried it with a real screen reader. For anything about actual announcements I would say you need a manual check, and I would verify the expected behaviour in the current WAI-ARIA Authoring Practices.

---

## Phase 6 — Performance (debounce vs throttle, caching, virtualization, pagination for feeds)

### 🟢 Beginner

**Q:** What is the difference between debounce and throttle?

**A:** Debounce waits until the events stop for a set time and then fires once, so a burst of keystrokes becomes a single call. Throttle fires at most once per interval while events keep coming, so it samples during the burst. For autocomplete I want debounce, because the intent is "the user paused, now show results". For scroll or resize handlers I would want throttle, because I need regular updates while the activity continues. My autocomplete doc chooses a window of roughly 150 to 200 ms as a trade-off between request spam and lag; those figures are design targets, not something I measured.

**Q:** What is virtualization and when do you need it?

**A:** Virtualization renders only the rows near the viewport plus a small overscan, and reuses DOM nodes as the user scrolls. I need it when a list is long enough that the DOM node count hurts scrolling; my news-feed doc frames it as protecting a 60 fps budget on a feed with thousands of posts. The Agent Console does not need it, because a chat transcript is short, and I have not added it. The honest rule is to reach for it when a measured list is slow, not by default.

### 🟡 Intermediate

**Q:** Show me a debounce you have written, and what is missing from it.

**A:** There is a generic `debounce` helper in my `next-js-app/lib/utils.ts`. It stores one timer, clears it on every call, and schedules the latest arguments. It is not used by the Agent Console, which has no search-as-you-type, and I found no caller of it elsewhere in that app's `app` and `components` folders. It has no `cancel` or `flush`, so a component that unmounts could still fire the delayed call. I would add a cancel and call it in an effect cleanup before using it in a React component.

**Source:** `next-js-app/lib/utils.ts:94-111`

```ts
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;

  return function executedFunction(...args: Parameters<T>) {
    const later = () => {
      timeout = null;
      func(...args);
    };

    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(later, wait);
  };
}
```

I would say debounce alone does not fix out-of-order responses: a slow request for "ca" can still arrive after "cat", so I pair it with `AbortController` and a request-id check, as my autocomplete doc and GFE guide both state.

**Q:** How would you cache and paginate a feed?

**A:** From my news-feed design: fetch pages with a cursor, not an offset, because inserts above the window make offset pagination duplicate or skip items. Put the pages behind a query cache such as TanStack Query for deduping and stale-while-revalidate, and normalise posts by id so a like touches one entity. Render only the visible slice with a virtualized list, and buffer new posts behind a "N new posts" pill instead of prepending. This is a design document; I have not built a feed, so I would present it as how I would approach it. At Couchbase I worked on React Query resilience (AV-144356 in my evidence inventory), which is the caching side of this, but I am not quoting that code here.

**Illustrative (not from the repo):**

```ts
export function createTokenBatcher(
  apply: (text: string) => void,
  schedule: (flush: () => void) => void,
) {
  let pending = "";
  let scheduled = false;

  function flush() {
    scheduled = false;
    if (pending === "") return;
    const text = pending;
    pending = "";
    apply(text);
  }

  return {
    push(token: string) {
      pending += token;
      if (!scheduled) {
        scheduled = true;
        schedule(flush);
      }
    },
    flush,
  };
}

export function visibleRange(
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  rowCount: number,
  overscan = 3,
) {
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const last = Math.min(rowCount - 1, Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan);
  return { first, last };
}
```

The `visibleRange` function is the core of windowing for fixed-height rows; variable-height rows need measured or estimated heights, which my design doc calls the harder, correct answer.

**Q:** How would you cache autocomplete results?

**A:** I would key a small least-recently-used cache by the normalised query string, so retyping a prefix after a backspace renders instantly. My design doc names an exact-match LRU as the safe default and client-side prefix filtering as a stretch optimisation. The doc also suggests a short time-to-live with a background refresh, because ranked results drift. The costs are stale suggestions and some memory, which I accept for a bounded cache; the capacity and TTL numbers in the doc are design choices that I have not tuned against real traffic.

**Illustrative (not from the repo):**

```ts
export class LruCache<V> {
  private readonly entries = new Map<string, V>();

  private readonly capacity: number;

  constructor(capacity: number) {
    this.capacity = capacity;
  }

  get(key: string): V | undefined {
    const value = this.entries.get(key);
    if (value === undefined) return undefined;
    this.entries.delete(key);
    this.entries.set(key, value);
    return value;
  }

  set(key: string, value: V): void {
    this.entries.delete(key);
    this.entries.set(key, value);
    if (this.entries.size > this.capacity) {
      const oldest = this.entries.keys().next().value as string;
      this.entries.delete(oldest);
    }
  }
}
```

The `Map` keeps insertion order, so deleting and re-inserting on read moves an entry to the newest position, and the first key is always the oldest; I tested eviction order in the scratchpad.

### 🔴 Senior

**Q:** Your answer re-renders on every token. Is that a performance problem?

**A:** I have not measured it, so I can only reason from the code. Every `token` action creates a new turns array, `TurnView` is not wrapped in `React.memo`, and I believe `ReactMarkdown` re-parses the answer string on each render (verify in its docs), including the earlier turns that have not changed. The only number I have for event rate is from note 02: 46 completion tokens in 1680 ms, which is roughly 27 tokens per second on a small local model, and I computed that division myself. At that rate a per-token render is probably fine for short answers; a faster hosted model or a long transcript is where I would expect it to bite. The first fix I would try is batching tokens per animation frame, then memoising finished turns, and I would measure with the React Profiler before and after.

The batcher in the `perf.ts` snippet above does the first fix: `push` accumulates text and schedules one flush, so many tokens per frame become one reducer action, and the injected scheduler lets a test drive it without a browser.

**Follow-up they will ask:** What is the cost of batching tokens?

**A:** The cost is a small delay of at most one frame before text appears, and a new place where timing can go wrong: pending text must be flushed before `done`, `error` or `abort`, or the tail of the answer is lost. That is why the sketch exposes `flush`. I would only add it after profiling shows a problem, since my current design is simpler and easier to reason about.

**Q:** How do you stop a slow old request from overwriting a fresh one?

**A:** Debounce only reduces how many requests I send. The out-of-order problem needs cancellation and a guard: abort the previous request when a new one starts, and also check an id before rendering, because an abort can lose a race against a response that has already resolved. My GFE notes say debouncing alone does not fix this, and my autocomplete design uses the abort-plus-id pair for the same reason. The failure mode without it is the latest query showing the results of an older query, which looks like the search is broken. I tested the helper below only for its bookkeeping, not against a real network.

**Illustrative (not from the repo):**

```ts
export function createLatestOnly() {
  let current = 0;
  let controller: AbortController | null = null;

  return {
    begin(): { id: number; signal: AbortSignal } {
      controller?.abort();
      controller = new AbortController();
      return { id: ++current, signal: controller.signal };
    },
    isCurrent(id: number): boolean {
      return id === current;
    },
  };
}
```

**Follow-up they will ask:** Does this guard apply to the streaming chat?

**A:** In the console I avoid the problem by construction, because the input is disabled while a turn streams, so there is never more than one request in flight. The unmount cleanup and the `finally` check on the controller reference cover the remaining cases. If I let the user send while a turn is running, I would need an id on each turn and the same latest-only discipline, plus a decision about whether the older turn is aborted or allowed to finish.

---

## Phase 7 — Testing UI logic (reducer unit tests, mocking the stream)

### 🟢 Beginner

**Q:** Why test the reducer instead of the component?

**A:** The reducer holds the rules, and it is a pure function, so a test is just "apply these actions, check the state". It needs no DOM, no server and no timers, and it runs in milliseconds. I run the tests with Node's built-in runner through `npm test`, and on 2026-10-20 I ran it and it reported 20 tests, 20 passing, in about 585 ms. Seven of those cover the SSE parser and thirteen cover the reducer and `toMessages`.

### 🟡 Intermediate

**Q:** How do you test streaming without a real network?

**A:** I build a `ReadableStream` from an array of string chunks, so the test decides exactly where the network "splits" the bytes. Then I feed it to `parseSSE` and collect the events. That lets me assert the three cases that matter: an event split across chunks, several events in one chunk, and a multi-byte character cut in the middle. A helper wraps the frame format so tests read as events, not escape sequences.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.test.ts:6-23`

```ts
/** Builds a ReadableStream from raw chunks, so we control exactly where the
 *  network "splits" the bytes. That split point is the whole point of these
 *  tests: a chunk is not an event. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const e of parseSSE(streamOf(chunks))) events.push(e);
  return events;
}
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.test.ts:38-45`

```ts
test("reassembles an event split across network chunks", async () => {
  // The bug that only appears under load: one read containing half an event.
  const whole = frame({ type: "token", value: "hello" });
  const events = await collect([whole.slice(0, 12), whole.slice(12)]);

  assert.equal(events.length, 1);
  assert.deepEqual(events[0], { type: "token", value: "hello" });
});
```

I would say the test names state the production bug each one prevents, and that the reducer tests use a tiny `run` helper that folds actions the way a real stream would.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts:6-9`

```ts
/** Applies a sequence of actions, the way a real stream would. */
function run(actions: Action[], from: State = initialState): State {
  return actions.reduce(reducer, from);
}
```

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts:61-67`

```ts
test("abort keeps what already streamed", () => {
  const state = run([askHello, { type: "token", value: "half an ans" }, { type: "abort" }]);

  assert.equal(state.status, "idle");
  assert.equal(state.turns[0].aborted, true);
  assert.equal(state.turns[0].answer, "half an ans", "deleting it would feel like a crash");
});
```

**Q:** How do you test the history sent back to the model?

**A:** The history rule is a pure function of the turns, so I build turns with the same action sequences a real stream would produce, call `toMessages`, and compare the exact message list. The important cases are that a failed answer, an aborted answer and the in-flight answer are all excluded. The failed-answer test also asserts that the partial text appears nowhere in the output, which is the property I actually care about. These are quick tests that protect a subtle prompt-quality bug, since a leaked half-answer would degrade the next response without any visible error.

**Source:** `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts:113-131`

```ts
test("toMessages excludes a failed answer from history", () => {
  // Replaying a failed turn as real assistant output poisons the next turn.
  const state = run([
    askHello,
    { type: "token", value: "broken half" },
    { type: "error", value: "boom" },
    { type: "ask", question: "next?" },
  ]);

  const messages = toMessages(state.turns);
  assert.equal(
    messages.some((m) => m.content === "broken half"),
    false,
  );
  assert.deepEqual(messages, [
    { role: "user", content: "hello?" },
    { role: "user", content: "next?" },
  ]);
});
```

**Q:** How would you test `streamChat` itself, which calls `fetch`?

**A:** The repo does not test `streamChat` today; its tests start at `parseSSE`. I would replace `globalThis.fetch` with a stub that returns a `Response` built from a `ReadableStream`, and assert both the happy path and that a 400 surfaces the server's text. In the scratchpad I ran the sketch below on Node 24 using the built-in `t.mock.method`, and both tests passed. I did not add it to the repo.

**Illustrative (not from the repo):**

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { streamChat, type StreamEvent } from "./chat.ts";

function sseResponse(frames: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f));
      controller.close();
    },
  });
  return new Response(body, { status });
}

async function collect(it: AsyncIterable<StreamEvent>) {
  const out: StreamEvent[] = [];
  for await (const e of it) out.push(e);
  return out;
}

test("streamChat yields events from a stubbed fetch", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    sseResponse(['data: {"type":"token","value":"hi"}\n\n', 'data: {"type":"done"}\n\n']),
  );
  const events = await collect(streamChat([{ role: "user", content: "q" }], new AbortController().signal));
  assert.deepEqual(events.map((e) => e.type), ["token", "done"]);
});

test("a 400 surfaces the server's plain-text reason", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("messages must not be empty\n", { status: 400 }));
  await assert.rejects(
    collect(streamChat([], new AbortController().signal)),
    /messages must not be empty/,
  );
});
```

I would describe this as mocking at the network boundary, which keeps the production code free of test-only injection.

### 🔴 Senior

**Q:** What is not covered by your 20 tests, and how would you close the gap?

**A:** The glue in `page.tsx` is untested: the `run` function, the abort race, the cleanup effect, the focus behaviour and anything rendered. There are no component tests, no end-to-end tests and no accessibility checks. The failure I found by reading, a stream that closes without a terminator, is exactly the kind of bug these tests would not have caught, since every reducer test supplies a terminator by hand. The cheapest improvement is to extract the loop and error handling out of the component into a function that takes an event source and a dispatch, then test it with fake generators. The trade-off is one more indirection against being able to test the abort rule, which is the most subtle piece of control flow in the page.

**Illustrative (not from the repo):**

```ts
import type { StreamEvent } from "./chat.ts";
import type { Action } from "./reducer.ts";

export async function consume(
  open: () => AsyncIterable<StreamEvent>,
  dispatch: (action: Action) => void,
  signal: AbortSignal,
): Promise<void> {
  try {
    for await (const event of open()) dispatch(event);
  } catch (err) {
    if (signal.aborted) return;
    dispatch({ type: "error", value: err instanceof Error ? err.message : "the stream failed" });
  }
}
```

**Illustrative (not from the repo):**

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { consume } from "./consume.ts";
import type { Action } from "./reducer.ts";
import type { StreamEvent } from "./chat.ts";

test("a transport failure becomes an error action", async () => {
  const seen: Action[] = [];
  const open = async function* (): AsyncGenerator<StreamEvent> {
    yield { type: "token", value: "a" };
    throw new Error("socket closed");
  };
  await consume(open, (a) => seen.push(a), new AbortController().signal);
  assert.deepEqual(seen, [
    { type: "token", value: "a" },
    { type: "error", value: "socket closed" },
  ]);
});

test("a failure after abort is not reported as an error", async () => {
  const seen: Action[] = [];
  const ac = new AbortController();
  const open = async function* (): AsyncGenerator<StreamEvent> {
    ac.abort();
    throw new DOMException("aborted", "AbortError");
  };
  await consume(open, (a) => seen.push(a), ac.signal);
  assert.deepEqual(seen, []);
});
```

Both tests passed in the scratchpad: a mid-stream failure becomes an `error` action, and a failure after abort dispatches nothing, which is the rule the page's `catch` block encodes.

**Follow-up they will ask:** How would you test abort deterministically?

**A:** I would not rely on real timing. I would create the `AbortController` in the test, give the fake stream a generator that waits on a promise I control, call `abort()` at a chosen point, and then assert what was dispatched. For the browser behaviour of cancelling a real `fetch`, a unit test cannot prove it, so I would add one end-to-end check against the server and look for the "client disconnected" log line, which is the evidence note 02 recorded for cancellation. I have not automated that check.

---

## Code reference index

| path:lines | what it shows |
|---|---|
| `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:19-24` | `StreamEvent` discriminated union mirroring the server |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:49-71` | Buffered SSE parse loop, malformed-frame skip |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.ts:86-108` | `streamChat`: POST, non-OK handling, hand-off to parser |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:9-29` | `Turn`, `State`, `Action` types |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:40-83` | The reducer cases (shown in two blocks) |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.ts:92-105` | `toMessages` excludes failed, aborted and in-flight answers |
| `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:16-24` | Unmount abort and auto-scroll effects |
| `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:26-62` | `run`, `ask`, `retry`, `stop` control flow |
| `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:104-135` | Labelled input, Send and Stop buttons |
| `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:157-172` | Status message and `react-markdown` rendering |
| `AI/fe-hands-on/app/agent-console-ui/app/page.tsx:202-223` | `Sources` in a native `<details>` |
| `AI/fe-hands-on/server/stream.go:18-33` | Server event struct and `Source` |
| `AI/fe-hands-on/server/stream.go:86-119` | Grounded prompt with the exact refusal sentence, citation numbering |
| `AI/fe-hands-on/server/stream.go:134-147` | `writeEvent` framing and flush |
| `AI/fe-hands-on/server/stream.go:177-232` | Headers, retrieval, `sources`, tokens, in-band `error`, `done` |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/chat.test.ts:6-73` | Fake byte stream and parser tests |
| `AI/fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts:6-152` | Reducer and `toMessages` tests |
| `AI/docs/notes/02-agent-console-sse-provider-seam.md` | SSE vs WebSocket reasoning and the recorded run numbers |
| `AI/interviews/frontend-system-design/autocomplete.md` | Debounce, cache, race guard, combobox ARIA design |
| `AI/interviews/frontend-system-design/news-feed.md` | Cursor pagination, virtualization, new-post pill design |
| `next-js-app/lib/utils.ts:94-111` | Generic `debounce` helper, unused by the console |

## Self-check

1. Why is a network chunk not an SSE event? Because one read can contain part of an event or several, so the parser must buffer until the blank-line terminator.
2. Why does the server report a mid-stream failure as an `error` event? Because the 200 status and headers are already sent and flushed tokens cannot be retracted.
3. What does the reducer do on `abort`, and why? It keeps the partial answer, marks the turn aborted and returns to idle, because discarding read text feels like a crash.
4. What happens today if the connection closes with no `done` or `error`? The reducer stays in `"streaming"` and the input stays disabled, which is a gap I found by reading and have not reproduced.
5. Why debounce plus abort, not debounce alone? Debounce reduces requests but does not stop a slow earlier response from arriving after a newer one.

## What not to claim

- I did not build reconnection, backoff or resume. The console has a manual Retry and nothing else.
- The `[n]` markers in answers are not clickable links, and sources are in a closed `<details>`. There is no citation validation and no refusal-specific UI.
- I have not audited `react-markdown` safety; verify the raw-HTML claim in the current docs.
- Autocomplete, the combobox, news feed, virtualization, pagination and debounce-in-use are designs and sketches, not shipped code in the Agent Console. The 150 to 200 ms debounce figure is a design target, not a measurement.
- I have not measured render cost, markdown re-parse cost or scroll jank. The 27 tokens per second figure is my own division of the numbers in note 02 from a small local model.
- There are no component, end-to-end or accessibility tests, and I have not tested with a screen reader. The twenty tests are parser and reducer logic only.
- The late-token-after-abort and clean-close-without-terminator problems are reasoned from the code, not reproduced.
- I did not read the Couchbase UI code for this module; the React Query resilience ticket (AV-144356) is cited only as an evidence-inventory entry.
- Note 02 still describes an earlier `EventSource` and `?q=` design and "6 Go tests"; the current code uses POST with `fetch`.
- EventSource reconnect and `Last-Event-ID` details and the exact ARIA authoring rules should be verified in current docs.
