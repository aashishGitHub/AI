# Module 09 (simple) — Frontend for AI products

> **Read this first**
> - **What it is for:** the browser side of an AI feature. Streaming words in, holding conversation state, stopping, showing evidence, access, speed, tests.
> - **Who it is for:** a beginner. No repo knowledge needed. Every term is explained the first time it shows up.
> - **Full version:** [09-frontend-ai-ui.md](../09-frontend-ai-ui.md) has the real code snippets and the harder follow-up questions.

Lane tags used here: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only.

- The Agent Console UI is **[L]**. It lives in [fe-hands-on/app/agent-console-ui/app/](../../../../fe-hands-on/app/agent-console-ui/app/) and talks to the Go server in [fe-hands-on/server/stream.go](../../../../fe-hands-on/server/stream.go).
- The autocomplete and news-feed material is **[K]**. It comes from paper designs in [autocomplete.md](../../../frontend-system-design/autocomplete.md) and [news-feed.md](../../../frontend-system-design/news-feed.md). Nothing there is built.
- Couchbase UI work is **[P]**. I only mention it in prose. I did not open that code for this module.

Versions named in the source (from the console's `package.json`): Next.js 16.3.2, React 19.2.8, `react-markdown` ^10.1.0.

---

## Phase 1 — Streaming fundamentals (SSE vs WebSocket vs polling, the event contract)

**Analogy: a sushi conveyor belt versus a sit-down meal.** Streaming is the belt. Each plate (a few words) reaches you as soon as the chef makes it. Non-streaming is waiting at the table until the whole meal is ready.

### Why stream at all
- Streaming means the server sends the answer in small pieces while the model is still writing it.
- The browser paints each piece the moment it arrives.
- What the user feels is **time to first token** (how long until the first word shows up).
- My own saved note recorded one local run. A short turn finished in 154 ms. A 46-token turn took 1680 ms.
- Without streaming, the user stares at nothing for up to that long. With streaming, words start almost at once.
- The user can also start reading early, or stop the answer early.

### SSE vs WebSocket vs polling
- **SSE** (Server-Sent Events) is a one-way pipe from server to browser over normal HTTP.
- I pick SSE for token streaming. Note 02 in my repo gives the reasoning: [02-agent-console-sse-provider-seam.md](../../../../docs/notes/02-agent-console-sse-provider-seam.md).
- **WebSocket** is a two-way connection. I do not need the two-way part. It also adds a second protocol to run and to pass through proxies.
- **Polling** means asking again and again ("is it ready yet?"). It adds delay equal to the poll gap, and wastes requests. It suits status checks, not live text.
- I would pick WebSocket only if the browser must push frequent messages on the same connection. Live collaboration is the example.

### The order of events and what ends a turn
- If retrieval is on, the server first sends one `sources` event.
- Then it sends many `token` events.
- Then it sends exactly one ending event: `done` or `error`.
- `done` carries usage numbers, so the UI can show prompt tokens, completion tokens and latency.
- If retrieval fails, the server sends `error` and no tokens.
- If the browser disconnects, the server sends nothing at all. Nobody is listening.
- So the UI can expect an ending event in normal use. It must not assume one in every failure. Phase 3 comes back to this.

### The event contract
- The contract is four JSON event types: `sources`, `token`, `done`, `error`.
- The TypeScript type on the client is a **discriminated union** (one type that is exactly one of several shapes, told apart by a `type` field). It mirrors the Go struct on the server.
- The UI never knows which model wrote the text. So I could swap model providers behind a Go interface without touching the frontend. Note 02 calls that the swap seam.
- The reducer's `Action` type includes the stream events directly. There is no translation layer between the network and the state.
- Each side has one definition of the contract. The types are the only coupling.
- Files: [chat.ts](../../../../fe-hands-on/app/agent-console-ui/app/lib/chat.ts) and [stream.go](../../../../fe-hands-on/server/stream.go).

### Why `fetch` with a `ReadableStream`, not `EventSource`
- `EventSource` is the browser's built-in SSE client. It can only send a GET with no body.
- Multi-turn history would have to be squeezed into the URL.
- I also could not cancel it as cleanly as a `fetch` driven by an `AbortController` (a switch that cancels a request).
- Note 02 predicted this. The first version used `?q=`. Multi-turn history forces POST plus `fetch` plus `ReadableStream`.
- The cost: I parse the SSE framing myself, and there is no built-in auto-reconnect.
- I accept that cost. History and cancellation matter most to the console.
- `streamChat` has two failure paths. A non-OK status arrives as plain text and becomes an `Error` with the server's reason. An OK status hands the body to the parser.
- Bad input gets plain text (4xx) because the server rejects it before it writes the event-stream headers.

### How the parser turns bytes into events
- I read chunks, decode them with a streaming `TextDecoder`, and add them to a string buffer.
- I emit an event only when I see the blank-line ending (`\n\n`).
- A network chunk is not an event. One read can hold half an event, or three.
- The `{ stream: true }` option stops a multi-byte character, split across two reads, from being corrupted.
- A malformed JSON frame is skipped. One bad frame must not kill a healthy answer.
- The tests feed the parser chunks cut at awkward points. That bug only shows up under load.

### What the server must do
- Set the event-stream content type.
- Turn caching off.
- Tell proxies not to buffer (`X-Accel-Buffering: no`).
- Flush after every event. Without a flush, bytes sit in Go's buffer until the handler ends. That defeats streaming.
- I only tested locally. I have not proven the proxy header against a real proxy.
- Lesson: if streaming shows up as one big lump, suspect a buffering layer, not the parser.
- The frame format `data: <payload>` plus a blank line is written in one place on the server and parsed in one place on the client.

### Senior: where the parser stops being correct
- The parser only handles my own server's style: single-line `data: <json>` frames split by `\n\n`.
- It does not handle `\r\n` line endings, multi-line `data:` fields, or the `event:`, `id:` and `retry:` fields.
- That is fine while I own both ends. It is a risk behind a proxy, or with a third-party stream.
- Trade-off: a small, fully tested parser versus full spec coverage.
- The failure is silent. A CRLF stream never finds `\n\n`, buffers forever, and the UI sits on "Searching the documentation" with no error.
- I have not measured this against a real proxy. I have not tested CRLF against the real parser.
- The hardening idea: replace the `\n\n` search with a boundary finder that accepts `\r\n`. Add tests for CRLF and for `: keep-alive` comment frames. The module shows a sketch (not in the repo).

### Senior: why mid-stream failure is an `error` event, not an HTTP status
- Once the server has sent the 200 status and headers, it cannot change the status.
- Tokens already flushed cannot be taken back.
- So the only honest channel is an in-band `error` event. Note 02 lists that as the cost of streaming.
- In `stream.go`, headers are written before retrieval runs. So even a retrieval failure arrives as a 200 carrying an `error` event.
- Only validation failures (before the headers) come back as real 4xx plain text.
- A client disconnect sends no frame at all, because nobody is listening.

### Senior: when is streaming the wrong choice?
- Streaming costs error-handling complexity.
- Skip it when the answer is short, when the user cannot act on partial output, or when the next step needs the whole result. A structured JSON payload is useless until it is whole.
- Once 200 tokens are flushed they cannot be retracted. So failures must be in-band.
- Abort, partial state and the "no ending event" problem exist only because of streaming.
- I have not measured a case where buffering would have been better. This is a design trade-off, not a benchmark.

### Words you'll hear
| Term | Meaning |
|---|---|
| Streaming | Server sends the answer in small pieces as the model writes it |
| Time to first token | Wait before the first word appears |
| SSE | One-way server-to-browser stream over plain HTTP |
| WebSocket | Two-way, long-lived connection |
| Polling | Asking repeatedly "is it ready yet?" |
| Event contract | The agreed list of event shapes both sides use |
| Discriminated union | A type that is one of several shapes, chosen by a `type` field |
| `AbortController` | A switch that cancels a `fetch` |
| Flush | Force buffered bytes out to the network now |
| In-band error | An error sent inside the same stream, not as an HTTP status |
| Terminator | The event that ends a turn: `done` or `error` |

**Say it in one breath:** I stream with SSE over `fetch` so words appear at once, I buffer bytes until a blank line, and a failure mid-answer travels as an `error` event because the 200 status is already sent.

---

## Phase 2 — State design (a pure reducer for a streaming conversation)

**Analogy: a restaurant order pad.** The waiter does not remember the table. Each event ("ordered soup", "cancelled soup") is written on the pad by fixed rules. Anyone can read the pad and know the table's state.

### Why a reducer
- A **reducer** is a plain function: (current state, action) in, next state out.
- All the rules live in one place.
- Every stream event and every user click becomes an **action** (a small message describing what happened).
- The component only dispatches actions and draws the result.
- I can test the rules with ordinary function calls. No DOM needed.
- My GFE guide (my own front-end interview notes) says: replace several booleans with one `status` enum. Booleans allow contradictory states. An enum cannot.

### What I store and what I derive
- I store the minimum: a `status` and a list of turns.
- Anything computable from those I work out while drawing. I do not sync it with an effect.
- Example: `streaming` is just `state.status === "streaming"`. The per-turn flag is that plus "is this the last turn".
- Benefit: no second source of truth that can drift away from the reducer.

### The state shape and the reducer
- `status` is `"idle"` or `"streaming"`.
- Each turn holds: the question, the answer so far, the sources, optional usage, optional error, optional `aborted` flag.
- `Action` is the union of `ask`, `abort`, `retry`, and the four stream events.
- `updateLast` copies the array and replaces only the last turn. Every streaming update targets the open turn.
- Nothing is mutated. React sees new references and re-draws.
- Three decisions to point at:
  - `done`, `error` and `abort` each return status to idle.
  - `abort` and `error` keep the partial answer.
  - `retry` replaces the failed turn. It does not add a dead entry.
- Sources arrive before the first token, so evidence is visible while the answer is written.
- File: [reducer.ts](../../../../fe-hands-on/app/agent-console-ui/app/lib/reducer.ts).

### `toMessages`: what the model is told
- It builds the request history from the stored turns.
- It leaves out any turn that errored, was aborted, or has an empty answer.
- It never sends the last turn's answer, because that turn is still being written.
- Replaying a half-answer as real assistant output would poison the next turn's context.
- What the user sees and what the model is told are two different views of the same turns.
- The server also caps history at 40 messages and 8000 characters per message in `Validate`. So the client rule is for correctness, not the security boundary.

### How I test retry
- Fold a short action list into a failed state. Apply `retry`. Check the result.
- Checks: still one turn, question kept, answer and error cleared, status streaming again.
- The first check is the design rule: a transient failure must not leave a dead entry.
- No component and no stream needed. Retry is a reducer action. The network call is made separately in the page.
- Each test name or message states the product rule, so the file reads like a spec. Test file: [reducer.test.ts](../../../../fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts).

### Senior: invariants the reducer should enforce
- **Invariant** (a rule that must always be true). Three apply here:
  - a turn ends exactly once;
  - stream events apply only while a turn is open;
  - an aborted turn keeps its partial text.
- My reducer enforces the first and third through status moves and tests.
- It does not enforce the second. A late `token` after `abort` would still be appended. The `token` case never checks `status`.
- Today that cannot happen in practice. Dispatches from one chunk run in a microtask chain before a click handler, and abort rejects the next read.
- I reasoned this from the code. I have not reproduced a late token. Treat it as an argument, not a measurement.
- Fix is cheap: a wrapper that drops stream events when status is idle. Trade-off: one more branch versus not depending on transport timing.

### Senior: what else is fragile
- Turns are identified only by array position. The page renders them with `key={i}`.
- That is safe for an append-only list. It breaks if I insert, delete or reorder.
- `retry` finds "the failed turn" as the last element. That assumes only the last turn can fail.
- Both hold today because the input is disabled while streaming. There is never more than one open turn.
- For concurrent questions I would give each turn an id, route events by id, and use per-turn status.

### Words you'll hear
| Term | Meaning |
|---|---|
| Reducer | Pure function: (state, action) gives the next state |
| Action | A small message saying what happened |
| Pure function | Same input always gives the same output, no side effects |
| Status enum | One field with a fixed list of values, instead of many booleans |
| Derived state | A value computed from stored state while drawing |
| Immutable update | Make a copy and change the copy, never the original |
| Invariant | A rule that must always hold |
| Poisoned context | Bad text in the history that makes later answers worse |

**Say it in one breath:** I keep the whole conversation in one pure reducer with a status enum, so every rule is testable without a browser, and half-answers never get replayed to the model.

---

## Phase 3 — Abort, errors and reconnection

**Analogy: a phone call.** Hanging up is you choosing to stop. A dropped line is a failure. You treat them differently. And a redial button is not an automatic reconnect.

### What Stop does
- The Stop handler calls `abort()` on the `AbortController` given to `fetch`.
- It also dispatches an `abort` action, so the UI updates at once.
- The browser cancels the request. My server's request context is cancelled when the client goes away, so the model stops generating.
- The partial answer stays on screen with a "Stopped." label.
- I keep it because deleting text the user was reading would feel like a crash.

### Control flow of one turn
- `ask` dispatches the `ask` action. Then `run` makes an `AbortController`, stores it in a ref, and loops over the stream with `for await`, dispatching each event.
- If something throws, the `catch` checks `controller.signal.aborted`.
- An abort is a user action. The reducer already recorded it. So I must not overwrite it with an error banner.
- Any other failure becomes an `error` action with the message.
- The `finally` clears the ref only if it still points at this controller. That protects a newer request's controller.
- An unmount cleanup aborts any in-flight request. Leaving the page stops the model, instead of leaking the stream.
- File: [page.tsx](../../../../fe-hands-on/app/agent-console-ui/app/page.tsx).

### How `ask` and `retry` build the request
- The component dispatches first, so the UI updates at once. Then it starts the network call with a history from `toMessages`.
- For retry, history is every turn except the failed one, plus that turn's question again.
- The reducer stays pure. The network call lives in the component.
- Caveat: both functions read `state.turns` from the render closure. That is correct only because input is disabled while streaming. Re-check it for concurrent turns.

### Failed request vs failed stream
- A failed request is a non-OK status. `streamChat` throws an `Error` with the server's plain-text reason. The `catch` in `run` dispatches it as `error`.
- A failed stream is an in-band `error` event. It goes through the same reducer case.
- Both end as `turn.error` with a Retry button. One recovery path for the user.
- Retry re-asks the same question through a reducer action that replaces the failed turn.

### Senior: does it have reconnection?
- No. It has a manual Retry that re-sends the whole question.
- No automatic reconnect, no backoff, no resume.
- A real gap I found by reading the code: if the connection closes cleanly with no `done` or `error`, `parseSSE` just finishes.
- Then `run` leaves its loop without dispatching. Status stays `"streaming"`. The input stays disabled until a page reload.
- A hard network drop is better. The read rejects, and `run` dispatches an error.
- I have not reproduced the clean-close case against the real server. The server always writes `done` or `error` unless the client is gone. I expect it only under proxy or crash conditions.
- The fix idea: a wrapper that turns "stream ended with no ending event" into an explicit `error` event.

### Senior: automatic retry and resume
- Automatic retry is safe only before the first event arrives. Nothing has been shown yet.
- After tokens are painted, a blind retry would duplicate or contradict the text. I would stop and show Retry.
- Resume mid-answer needs server support: event ids, a replay buffer, a way to continue generation. I have built none of it.
- I am not certain of the exact `EventSource` reconnect and `Last-Event-ID` rules. Verify them in the MDN docs before claiming them.
- Note 02 only says `EventSource` auto-reconnects. I gave that up by using `fetch`.
- The `received` flag in the retry sketch is the whole idea: it makes retry safe from the user's view.

### Words you'll hear
| Term | Meaning |
|---|---|
| Abort | Cancel an in-flight request on purpose |
| `finally` | Code that runs whether the `try` worked or threw |
| Ref | A React box that holds a value across renders without re-drawing |
| Backoff | Waiting longer between each retry |
| Reconnect | Re-opening a dropped stream, ideally automatically |
| Resume | Continuing from where the stream broke |
| `Last-Event-ID` | An SSE header for resuming (verify exact rules in MDN) |
| Unmount | The component leaves the screen |

**Say it in one breath:** Stop aborts the fetch and keeps the partial text, failures show a Retry button, and I have no auto-reconnect, so a stream that closes without an ending event would leave the UI stuck.

---

## Phase 4 — Trust UX (citations before tokens, markdown rendering, refusals)

**Analogy: a lawyer who hands you the case files before giving advice.** You can check the files while they talk. But having the files on the table does not prove the advice used them.

### Why sources come before the text
- A user who sees the evidence while the answer is being written can judge it, not just trust it.
- The server sends `sources` after retrieval and before any token. The reducer stores it on the turn.
- Honest limit: sources show what the model was given. They do not prove the answer used them correctly.

### Why render Markdown
- The model writes Markdown: fenced code, lists, tables.
- As plain text, every code block was unreadable. That is why the renderer was added.
- For a documentation assistant, the code blocks are the product. So readable code is a trust feature.
- Costs: a new dependency, and the question of safely rendering model output.

### How citations are drawn
- Sources sit in a native `<details>` element above the answer. The summary says how many sources the answer is grounded in.
- Each item is numbered `[1]`, `[2]` to match the `[n]` markers the prompt tells the model to use.
- Be precise: numbers match by convention. The `[n]` in the answer is plain Markdown text, not a clickable link.
- `<details>` is closed by default. Evidence is available but not forced.
- `<details>` gives keyboard and screen-reader behaviour for free.
- The missing link from `[n]` to its source is the first thing I would build next.

### How `[n]` numbers are matched
- On the server, `buildMessages` numbers each chunk `[1]`, `[2]` in the system prompt, and tells the model to cite by those numbers.
- The `sources` event carries the same chunks in the same order. The UI numbers by array index plus one.
- So the contract is positional. If one list were reordered or filtered and the other not, numbers would silently point at the wrong source.
- I have not written a test that locks that order across both sides.

### Rendering Markdown safely
- I use `react-markdown` with `remark-gfm` (tables and fenced code).
- A code comment claims `react-markdown` does not pass raw HTML through, so model output cannot inject markup.
- I did not add `rehype-raw`, the plugin that would change that.
- I have not audited link handling. I have not confirmed the claim in the current docs. Verify before calling it a security guarantee.
- Think of it as "the answer is data, drawn through a safe component".
- The pulsing cursor is the only streaming sign besides the status text.

### What the UI does on a refusal
- Nothing special. I should say that plainly.
- The server prompt tells the model to reply with the exact sentence "The provided documentation does not cover this." when the context lacks the answer.
- The UI draws that as ordinary Markdown. No refusal component, no styling, no "try rephrasing".
- The exact wording is a contract I could match on. Matching model output by string is brittle.

### Senior: being honest about bad citations
- After a turn ends, extract every `[n]` and check `n` is between 1 and the number of sources.
- An out-of-range number is a cheap, concrete sign of a bad answer. Show a visible warning.
- Give the exact refusal sentence its own layout. A refusal that looks like a normal answer teaches users to ignore it.
- Limit: this only catches malformed citations. It cannot tell if a correct-looking `[2]` supports the claim. That is an evaluation problem. My eval harness is where it belongs.
- I have not built either check in the console.
- Matching the refusal by string is a deliberate coupling to the server prompt. A structured `refusal` flag would be better if the contract can change.

### Senior: why show sources if the model may ignore them
- The UI claims only "this is what the model was given". The summary says "the answer is grounded in these".
- That wording is slightly stronger than I can prove. I would soften it if a customer relied on it.
- Ordering still helps. In `stream.go`, a retrieval error produces an `error` event. It never falls back to an ungrounded answer. The server comment calls that the confident-hallucination path.

### Words you'll hear
| Term | Meaning |
|---|---|
| Citation | A pointer like `[2]` from the answer to a source |
| Grounded | Answer based on supplied documents, not the model's memory |
| Retrieval | Fetching relevant document chunks before answering |
| Refusal | The model saying it cannot answer from the context |
| `<details>` | Native HTML collapse/expand element |
| Markdown | Plain-text format for headings, lists and code |
| `rehype-raw` | A plugin that lets raw HTML through (I do not use it) |
| Hallucination | A confident answer that is made up |

**Say it in one breath:** I show the evidence before the answer and render Markdown safely, but citations are not clickable, refusals look like normal text, and sources prove what the model was given, not what it used.

---

## Phase 5 — Accessibility and keyboard interaction (autocomplete combobox pattern)

**Analogy: a hotel lobby with a good concierge desk.** Anyone can use it by voice, touch or keyboard. The signs are real signs, not paintings of signs. Screen readers are the guests who cannot see the signs.

### What the console already has
- The input has a real `<label>`, visually hidden with `sr-only`.
- Send and Stop are real `<button>` elements.
- The "Searching the documentation" message has `role="status"` (tells assistive tech it is a status message).
- Sources use native `<details>` and `<summary>`, which work from the keyboard.
- I have not run an automated audit or tested with a screen reader. So I claim semantic elements, not "accessible".

### Why two buttons
- Stop shows only while streaming, the only time it means anything. It aborts the request. It does not just hide output.
- Send is the form's submit button. It is disabled when the input is empty.
- Both are real buttons, so keyboard works without extra code.
- The submit handler refuses to run while streaming. A second question cannot start while a turn is open.
- Weak spot: the two buttons swap in the same place. I have not checked where keyboard focus goes when Send is replaced by Stop.

### The ARIA pattern for autocomplete
- **ARIA** (attributes that tell assistive tools what a widget is). My autocomplete design doc describes a `combobox` input that controls a `listbox` of `option` items.
- Arrow keys move a highlighted option. Enter selects. Escape closes without selecting.
- The key detail: the highlight is tracked with `aria-activedescendant`. Real focus stays in the input, so typing is never interrupted.
- The input also has `aria-expanded`, `aria-controls` and `aria-autocomplete="list"`. A polite live region announces the result count.
- This comes from my own design doc. Verify against current WAI-ARIA Authoring Practices before quoting it as spec.
- The module's sketch keeps keyboard logic in a pure reducer, with ARIA attributes as a thin projection of that state. It is **not** in the Agent Console. I tested the reducer, not the component in a browser.

### Why `aria-activedescendant`, not moving focus
- Moving DOM focus to each option pulls focus out of the input. The caret and input-method composition would be lost on every arrow press.
- With `aria-activedescendant`, focus stays on the input, and the attribute names the current option.
- My design doc calls this the detail that separates people who built it from people who guessed.
- Cost: ids must stay unique and in sync. The sketch uses `useId`.

### Senior: streaming answer and screen readers
- Do not put the whole streaming answer in an `aria-live` region. Announcing every token is unusable.
- My judgment: announce a short status at the start (the existing "Searching") and a short "answer complete" on `done`. Let the text be read normally.
- I have not tested this with a screen reader. It is a hypothesis.
- Gaps I see: the input is disabled while streaming, which can drop keyboard focus. Nothing restores focus after the turn ends.
- Trade-off: announcement noise versus the user not knowing anything happened.

### Senior: auto-scroll
- The console scrolls to the bottom in an effect that depends on `state.turns` and `state.status`. It runs on every token.
- It will pull the user back down if they scrolled up to re-read.
- `block: "end"` avoids yanking a short page. It does not respect the user's scroll position.
- My news-feed doc states the principle: never change what is in the viewport without user consent.
- Fix: follow only while the user is near the bottom. Otherwise show a "jump to latest" control.

### Senior: testing the combobox
- Two layers. Keyboard logic is a pure reducer: test moves, wrap-around and close.
- For ARIA wiring: render the component and query by role and attribute with Testing Library. My design doc recommends that over querying internals.
- I ran reducer tests for my sketch in a scratch area. I have not run a component test or tried a real screen reader.
- For real announcements, you need a manual check. Verify expected behaviour in the current WAI-ARIA Authoring Practices.

### Words you'll hear
| Term | Meaning |
|---|---|
| ARIA | Attributes that describe a widget to assistive tech |
| Combobox | An input with a pop-up list of choices |
| Listbox / option | The list and its items inside a combobox |
| `aria-activedescendant` | Names the highlighted option while focus stays in the input |
| `aria-live` | A region whose changes are announced by screen readers |
| `sr-only` | Hidden on screen, still read by screen readers |
| Focus | Which element receives keyboard input right now |
| Semantic element | A real HTML element with built-in meaning (`button`, `label`) |

**Say it in one breath:** I use real labels, buttons and `<details>`, I know the combobox pattern keeps focus in the input via `aria-activedescendant`, and I have not tested with a screen reader.

---

## Phase 6 — Performance (debounce vs throttle, caching, virtualization, pagination for feeds)

**Analogy: a lift button and a bus timetable.** Debounce is a lift that waits until people stop pressing the button before it moves. Throttle is a bus that leaves every ten minutes no matter how many people arrive.

### Debounce vs throttle
- **Debounce** waits until events stop for a set time, then fires once. A burst of keystrokes becomes one call.
- **Throttle** fires at most once per interval while events keep coming. It samples during the burst.
- Autocomplete wants debounce: "the user paused, now show results".
- Scroll or resize handlers want throttle: I need regular updates while the action continues.
- My autocomplete doc picks roughly 150 to 200 ms, a trade-off between request spam and lag. Those are design targets, not measurements.

### Virtualization
- **Virtualization** draws only the rows near the viewport plus a small extra (overscan). It reuses DOM nodes while scrolling.
- Needed when a list is long enough that DOM node count hurts scrolling.
- My news-feed doc frames it as protecting a 60 fps budget on a feed of thousands of posts.
- The Agent Console does not need it. A chat transcript is short. I have not added it.
- Rule: reach for it when a measured list is slow, not by default.

### My debounce helper
- There is a generic `debounce` in `next-js-app/lib/utils.ts` (a sibling repo, outside this one).
- It keeps one timer, clears it on every call, and schedules the latest arguments.
- The Agent Console does not use it. I found no caller in that app's `app` and `components` folders.
- It has no `cancel` or `flush`. A component that unmounts could still fire the delayed call.
- I would add `cancel` and call it in an effect cleanup before using it in React.
- Debounce alone does not fix out-of-order responses. A slow request for "ca" can arrive after "cat". I pair it with `AbortController` and a request-id check, as my autocomplete doc and GFE guide say.

### Caching and paginating a feed (paper design, [K])
- Use a **cursor** (a bookmark pointing at "the item after this one"), not an offset. Inserts above the window make offset pagination duplicate or skip items.
- Put pages behind a query cache such as TanStack Query for deduping and stale-while-revalidate (show old data, refresh quietly).
- Normalise posts by id so a like touches one entity.
- Render only the visible slice with a virtualized list.
- Buffer new posts behind a "N new posts" pill instead of prepending.
- This is a design document. I have not built a feed. At Couchbase I worked on React Query resilience (AV-144356, from my evidence inventory, **[P]**). I am not quoting that code here.
- For fixed-height rows, `visibleRange` is the core of windowing. Variable-height rows need measured or estimated heights, the harder and correct answer.

### Caching autocomplete results
- Use a small **LRU cache** (least-recently-used: when full, drop the entry unused the longest), keyed by the normalised query string.
- Retyping a prefix after a backspace then shows instantly.
- My doc names an exact-match LRU as the safe default and client-side prefix filtering as a stretch.
- It also suggests a short time-to-live with a background refresh, because ranked results drift.
- Costs: stale suggestions and some memory. I accept those for a bounded cache.
- The capacity and TTL numbers in the doc are design choices. I have not tuned them on real traffic.
- A JavaScript `Map` keeps insertion order. Deleting and re-inserting on read moves an entry to newest. The first key is always the oldest. I tested eviction order in a scratch area.

### Senior: re-render on every token
- I have not measured it. I can only reason from the code.
- Every `token` action makes a new turns array. `TurnView` is not wrapped in `React.memo`. I believe `ReactMarkdown` re-parses the answer on each render (verify in its docs), including earlier unchanged turns.
- The only rate figure: note 02 shows 46 completion tokens in 1680 ms, about 27 tokens per second on a small local model. I did that division myself.
- At that rate a per-token render is probably fine for short answers. A faster hosted model or a long transcript is where it would bite.
- First fix: batch tokens per animation frame. Then memoise finished turns. Measure with the React Profiler before and after.
- The batcher collects text and schedules one flush, so many tokens per frame become one reducer action.
- Cost of batching: up to one frame of delay. And pending text must be flushed before `done`, `error` or `abort`, or the tail of the answer is lost.
- I would only add it after profiling shows a problem. The current design is simpler.

### Senior: stopping a slow old request overwriting a fresh one
- Debounce only reduces how many requests I send.
- The fix needs cancellation plus a guard: abort the previous request when a new one starts, and also check an id before rendering. An abort can lose a race against a response that has already resolved.
- Without it, the latest query shows the results of an older query. It looks like search is broken.
- I tested the helper only for its bookkeeping, not on a real network.
- In the streaming chat I avoid the problem by construction. The input is disabled while a turn streams, so only one request is in flight.
- If the user could send during a turn, I would need an id per turn, the same latest-only rule, and a decision: abort the older turn or let it finish.

### Words you'll hear
| Term | Meaning |
|---|---|
| Debounce | Wait for a pause, then fire once |
| Throttle | Fire at most once per interval |
| Virtualization | Draw only the rows near the viewport |
| Overscan | Extra rows drawn just outside the viewport |
| Cursor pagination | Next page is "after this item", not "skip N" |
| LRU cache | Cache that drops the least recently used entry |
| TTL | Time-to-live: how long a cached item is valid |
| Stale-while-revalidate | Show old data now, fetch fresh data in the background |
| Memoise | Reuse the last result if the inputs did not change |
| Race condition | Two things finish in an unexpected order |

**Say it in one breath:** I debounce plus abort for autocomplete, use cursors and virtual lists on paper for feeds, and I have not measured per-token render cost, so I would profile before batching.

---

## Phase 7 — Testing UI logic (reducer unit tests, mocking the stream)

**Analogy: testing the engine on a bench, not on the motorway.** The reducer and parser are engines I can run on a bench with fake fuel. The page glue is the car, and I have not road-tested it.

### Why test the reducer, not the component
- The reducer holds the rules and is a pure function. A test is "apply these actions, check the state".
- No DOM, no server, no timers. It runs in milliseconds.
- I run tests with Node's built-in runner through `npm test`.
- On 2026-10-20 I ran it: 20 tests, 20 passing, about 585 ms.
- Seven cover the SSE parser. Thirteen cover the reducer and `toMessages`.

### Testing streaming without a network
- Build a `ReadableStream` from an array of string chunks. The test chooses exactly where the "network" splits the bytes.
- Feed it to `parseSSE`. Collect the events.
- Three cases matter: an event split across chunks, several events in one chunk, a multi-byte character cut in the middle.
- A small helper wraps the frame format, so tests read as events, not escape sequences.
- Test names state the production bug each one prevents.
- Reducer tests use a tiny `run` helper that folds actions the way a real stream would.
- Files: [chat.test.ts](../../../../fe-hands-on/app/agent-console-ui/app/lib/chat.test.ts), [reducer.test.ts](../../../../fe-hands-on/app/agent-console-ui/app/lib/reducer.test.ts).

### Testing the history sent to the model
- The history rule is a pure function of the turns.
- Build turns with the same actions a real stream would produce. Call `toMessages`. Compare the exact list.
- Cases: a failed answer, an aborted answer and the in-flight answer are all excluded.
- The failed-answer test also checks the partial text appears nowhere in the output. That is the property I care about.
- These are quick tests that protect a subtle prompt-quality bug. A leaked half-answer would worsen the next response with no visible error.

### Testing `streamChat` itself
- The repo does not test `streamChat` today. Its tests start at `parseSSE`.
- I would swap `globalThis.fetch` for a stub returning a `Response` built from a `ReadableStream`.
- Check the happy path, and that a 400 surfaces the server's text.
- In a scratch area I ran this on Node 24 with the built-in `t.mock.method`. Both tests passed. I did not add it to the repo.
- This is mocking at the network boundary. Production code stays free of test-only hooks.

### Senior: what the 20 tests do not cover
- The glue in `page.tsx` is untested: `run`, the abort race, the cleanup effect, focus behaviour, anything rendered.
- No component tests, no end-to-end tests, no accessibility checks.
- The bug I found by reading (a stream closing with no ending event) is the kind these tests miss. Every reducer test supplies an ending event by hand.
- Cheapest improvement: pull the loop and error handling out of the component into a function taking an event source and a dispatch. Test it with fake generators.
- Trade-off: one more layer of indirection versus being able to test the abort rule, the most subtle control flow in the page.
- Two scratch tests passed: a mid-stream failure becomes an `error` action, and a failure after abort dispatches nothing.

### Senior: testing abort deterministically
- Do not rely on real timing.
- Create the `AbortController` in the test. Give the fake stream a generator that waits on a promise I control. Call `abort()` at a chosen point. Check what was dispatched.
- A unit test cannot prove a real `fetch` cancel in a browser. I would add one end-to-end check against the server and look for the "client disconnected" log line. Note 02 recorded that as the evidence for cancellation.
- I have not automated that check.

### Words you'll hear
| Term | Meaning |
|---|---|
| Unit test | Test of one small piece, no network or browser |
| `ReadableStream` | A browser stream of bytes you read piece by piece |
| Fake / stub | A stand-in object that returns fixed answers |
| Mock at the boundary | Replace only the outermost call (like `fetch`) |
| End-to-end test | Test the whole app as a user would |
| Fold | Apply a list of actions one after another to a state |
| Test seam | A place where code can be cut apart for testing |

**Say it in one breath:** I test the parser and reducer with fake byte streams, 20 of 20 passed on 2026-10-20, but the page glue, abort race, focus and accessibility have no tests.

---

## Mix-ups to avoid

- A network **chunk** is not an SSE **event**. One read can hold half an event or several.
- **Retry** is not **reconnect**. I built a manual button that re-sends the question. I built no auto-reconnect, backoff or resume.
- **Debounce** is not **throttle**. Debounce waits for a pause. Throttle samples at a steady rate.
- **Debounce alone** does not stop a slow old response from landing after a new one. You also need abort plus an id check.
- **Sources shown** is not **sources used**. They show what the model was given, not what it relied on.
- The `[n]` markers are matched **by position**. They are not clickable links.

## What I built vs what I only know

**Built (my own, lane [L]):**
- The Agent Console UI: SSE over `fetch`, the parser, the reducer, `toMessages`, Stop and manual Retry, sources in `<details>`, Markdown rendering.
- Twenty parser and reducer tests (7 parser, 13 reducer and `toMessages`). Ran 20 of 20 on 2026-10-20.

**Knowledge or paper design only ([K], not built):**
- Autocomplete, the combobox, the news feed, virtualization, cursor pagination, and debounce in real use. The 150 to 200 ms debounce figure is a design target, not a measurement.
- Reconnection, backoff and resume. I did not build any of it.
- Citation validation and any refusal-specific UI. Neither exists in the console.

**Not claimed:**
- I have not audited `react-markdown` safety. Verify the raw-HTML claim in the current docs.
- No measurement of render cost, markdown re-parse cost or scroll jank. The 27 tokens per second is my own division of note 02's numbers, from a small local model.
- No component, end-to-end or accessibility tests. No screen reader test.
- The late-token-after-abort and clean-close-without-terminator problems are reasoned from the code, not reproduced.
- Couchbase UI **[P]**: I did not read that code for this module. The React Query ticket AV-144356 is cited only as an evidence-inventory entry.
- Note 02 still describes an earlier `EventSource` and `?q=` design and "6 Go tests". The current code uses POST with `fetch`.
- EventSource reconnect and `Last-Event-ID` details, and the exact ARIA authoring rules, should be verified in current docs.
