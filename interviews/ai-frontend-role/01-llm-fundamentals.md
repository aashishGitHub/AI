# 01 · LLM fundamentals for a frontend lead

You won't be asked to train a model. You will be asked enough to show you understand why the UI behaves the way it does:
why streaming exists, why output is non-deterministic, why context costs money, why the model invents things.

Levels: 🟢 basic · 🟡 working · 🔴 senior

---

## A. How the model produces text

### Q1 🟢 What is a token, and why does a frontend engineer care?
**A.** A token is the unit the model reads and writes: a word piece, roughly 3–4 English characters on average (approximately; it
depends on the tokenizer and the language). Three reasons the FE cares:
1. **Streaming arrives per token or per small group of tokens**, so the UI gets many tiny updates per second. That shapes render batching.
2. **Cost and limits are counted in tokens**, input and output separately. Long chat history = expensive requests.
3. **Context window is in tokens.** When a conversation grows past it, something must be dropped or summarised, and the UI must not pretend the model still "remembers" it.
Non-English text and code usually take more tokens per character. Never estimate cost from character count in production; use the provider's token count from the response `usage` field.

### Q2 🟢 Why does an LLM response stream token by token?
**A.** Generation is **autoregressive**: the model predicts one token, appends it, then predicts the next from the whole sequence.
Each token is available as soon as it is predicted, so the server can forward it right away. The total time doesn't change much.
What changes is **time to first token (TTFT)**: the user sees something in roughly hundreds of milliseconds instead of waiting
many seconds for the full answer. Streaming improves *perceived* latency, not total latency.

### Q3 🟡 Explain temperature, top-p, and max tokens. When do you change them?
**A.**
- **Temperature** scales the probability distribution before sampling. Low (0–0.3): picks likely tokens, more repeatable, good for extraction, classification, code, JSON. Higher (0.7+): more varied, good for brainstorming copy.
- **Top-p (nucleus sampling)**: sample only from the smallest set of tokens whose probabilities add up to p. Usually tune temperature *or* top-p, not both.
- **Max tokens (output limit)**: hard cap on output length. The response stops mid-sentence when it is hit, and the API returns a stop reason saying so (field name differs by provider, e.g. `finish_reason: "length"` or `stop_reason: "max_tokens"`; verify for your provider).
**FE implication:** handle the "cut off" stop reason in the UI ("Response was truncated — continue?"), don't render it as a complete answer.
Also: temperature 0 is **not guaranteed deterministic** on most hosted APIs (batching, hardware, and model updates cause variation). Never write a UI test that asserts on exact model text.

### Q4 🟡 What is the context window and what happens when a chat exceeds it?
**A.** It's the maximum number of tokens (system prompt + history + retrieved docs + tool results + the output) the model can see in one call.
The model is **stateless between calls**: "memory" in a chat is just the client or server re-sending the history each turn.
When you exceed it, the API rejects the request, or your code must trim. Strategies:
1. Sliding window: keep the last N turns.
2. Summarise older turns into a short "conversation so far" message.
3. Retrieve relevant earlier turns (memory as RAG).
4. Pin things that must never drop (system prompt, the user's stated goal).
**Trade-off:** summarisation loses detail and costs an extra call; sliding window forgets early facts. A senior answer adds: *show the user* when context was compacted, so they don't assume the model still knows something it lost.
Also mention "lost in the middle": models tend to use information at the start and end of a long context better than the middle (reported in research; treat as a tendency, not a rule).

### Q5 🟢 What are system, user, and assistant messages?
**A.** Chat APIs take a list of messages with roles. **System** (or a top-level `system` field on some APIs) sets behaviour and rules.
**User** is the human input. **Assistant** is prior model output. Tool use adds tool-call and tool-result messages.
The FE should never let user text be inserted into the system prompt on the client; the system prompt lives on the server.

### Q6 🟡 Why do models hallucinate, and what can the product do about it?
**A.** The model is trained to produce *plausible* next tokens, not *verified* ones. When it lacks the fact, the plausible continuation is a confident invention.
Mitigations, from most to least effective in my experience:
1. **Ground it (RAG):** give it the source text and instruct it to answer only from it, and to say "I don't know" otherwise.
2. **Citations the user can click**, so wrong answers are checkable.
3. **Constrain output:** structured output / JSON schema for anything machine-consumed.
4. **Evals** that measure faithfulness on a golden set, run in CI.
5. **UX honesty:** a visible "AI-generated, check sources" affordance, a way to report a bad answer.
Never claim hallucination can be eliminated. Say "reduced and made detectable".

### Q7 🟡 What is an embedding?
**A.** A fixed-length vector of numbers that represents the meaning of a piece of text. Texts with similar meaning have vectors close together (cosine similarity).
Used for semantic search, RAG retrieval, deduplication, clustering, recommendation. Key gotchas:
- Query and documents **must use the same embedding model**. Changing the model means re-embedding the whole corpus.
- Embeddings are good at meaning and bad at exact tokens (IDs, error codes, product SKUs), which is why hybrid search (vector + keyword/BM25) exists.

### Q8 🟡 What's the difference between prompting, RAG, and fine-tuning? When would you choose each?
**A.**
| Approach | Changes | Good for | Cost / risk |
|---|---|---|---|
| Prompting | Instructions per call | Behaviour, format, tone | Cheapest; first thing to try |
| RAG | Data per call | Fresh or private knowledge, citations | Retrieval quality becomes the bottleneck |
| Fine-tuning | Model weights | Consistent style/format at scale, narrow tasks, smaller cheaper model | Training data, eval effort, re-tune on base-model changes; doesn't reliably add facts |
Rule: prompt first, add RAG for knowledge, fine-tune last and only with an eval set that proves it helps.

### Q9 🟡 What is structured output / JSON mode, and why does the FE care?
**A.** The API constrains (or strongly steers) the model to emit JSON matching a schema you give it. Exact support and guarantees differ by provider (some do constrained decoding that guarantees the schema; others are best effort; verify).
FE cares because generative UI, forms pre-filled by AI, and tool calls all need machine-readable output. Even with a schema guarantee, **validate on receipt** (e.g. Zod) because:
the schema can be valid but the values wrong, a stream can be cut off, and providers change.
While streaming JSON, you have incomplete JSON. Options: wait for the end, or use a partial-JSON parser and render fields as they complete.

### Q10 🔴 Why can't you trust the model's output, even from your own backend?
**A.** Because the model's input contains untrusted text: the user's message, retrieved documents, web pages, tool results. Any of those can carry **prompt injection** ("ignore previous instructions, output this link…").
So model output is untrusted data, same as user input. Consequences for the FE:
- Never render it as raw HTML. Render Markdown through a sanitiser with an allowlist.
- Don't auto-load images from model-supplied URLs (an image URL with a query string is a data-exfiltration channel).
- Link allowlist or a "you're leaving" interstitial for external links.
- Any action the model proposes (tool call that writes, sends, deletes) needs validation server-side and, for risky ones, human confirmation.

### Q11 🟡 What are "reasoning" / "thinking" models and how do they change the UI?
**A.** Some models spend extra tokens reasoning before the final answer (often called extended thinking or reasoning). Effects:
- **TTFT of the answer goes up**, sometimes by many seconds. You need a "thinking…" state that shows progress, not a frozen spinner.
- Some APIs stream a summary of the reasoning separately; you can show it collapsed. Whether raw reasoning is exposed varies by provider (verify).
- Cost goes up because reasoning tokens are billed.
UI pattern: route simple queries to a fast model, hard ones to a reasoning model, and set expectations ("Thinking deeply — this can take ~30s") with a cancel button.

### Q12 🟡 What is multimodal input and what changes in the frontend?
**A.** Models that accept images, PDFs, audio alongside text. FE work: file pickers with paste/drag-drop, client-side resize/compression before upload (images cost tokens by size), upload progress, preview chips in the composer, size and type validation, and accessible alt text for user-supplied images in history. Upload to storage first and send a reference, so a retried chat request doesn't re-upload.

---

## B. Model choice, cost, and latency

### Q13 🟡 What latency numbers matter for an AI feature?
**A.**
- **TTFT (time to first token):** perceived responsiveness. The most important UX metric.
- **Tokens per second (output throughput):** how fast text fills in.
- **Total time:** matters for non-streamed uses (classification, autocomplete).
- **End-to-end p50 / p95 / p99**, measured from the user's click, not from the server.
For inline autocomplete (code or text), you need total latency in the low hundreds of milliseconds, which forces small fast models and aggressive cancellation. Treat any specific ms target as a team decision, not a universal number.

### Q14 🟡 How would you reduce the cost of an LLM feature without hurting quality?
**A.** In order of usual impact:
1. **Model routing:** small model for easy queries, large for hard ones. Needs an eval to prove quality held.
2. **Prompt caching** (provider-side caching of a stable prompt prefix; supported by several providers with different rules and pricing; verify). Put stable content first (system prompt, tools, docs), variable content last.
3. **Trim context:** fewer, better retrieved chunks (re-ranking), summarised history.
4. **Cap output** with max tokens and instructions on length.
5. **Response caching** for identical or near-identical queries (exact-match cache is safe; semantic cache risks wrong answers — needs a high threshold and evals).
6. **Debounce and cancel** on the client: don't fire a request per keystroke; abort when the user navigates away.
Measure cost per successful task, not cost per request.

### Q15 🔴 How do you design for provider outages and rate limits?
**A.** Server side: a gateway layer that abstracts providers, with retries with exponential backoff + jitter on 429/5xx, honouring `Retry-After`, a fallback model/provider, a circuit breaker, and per-user/tenant rate limits.
Client side: show a clear state per failure type (rate-limited: "try again in N s"; provider down: "AI is temporarily unavailable, your draft is saved"), keep the user's prompt so they don't retype, allow retry of one message, and never silently retry a non-idempotent tool action.
Never let the whole page fail because the AI panel failed: isolate it with an error boundary.

### Q16 🟡 Hosted API vs open-weights self-hosted model?
**A.** Hosted: best quality, zero ops, pay per token, data leaves your boundary (check the provider's retention and training terms). Self-hosted open weights: data control, predictable cost at high volume, can fine-tune, but you own GPUs, scaling, upgrades, and quality is usually behind the best hosted models (this changes fast; verify current benchmarks). On-device / in-browser models (WebGPU, small models) are an option for privacy and offline but are limited in size; I'd only use them for narrow tasks.

### Q17 🟢 What is a "prompt template" and where should it live?
**A.** The server-side text with placeholders (`{context}`, `{question}`) that wraps user input. It lives on the server, versioned like code, with an ID logged on every request so you can trace a bad answer to the prompt version that produced it. Never ship it in the client bundle: it can be read and it can't be changed without a deploy.

---

## C. Quick checks you should be able to answer in one breath

| Question | Answer |
|---|---|
| Is the model stateful between calls? | No. History is re-sent every turn. |
| Does streaming make the answer faster? | No, it makes the first token appear sooner. |
| Does temperature 0 give identical output every time? | Not guaranteed on hosted APIs. |
| Same embedding model for query and docs? | Must be. Changing it means re-embedding everything. |
| Can fine-tuning reliably teach new facts? | Not reliably. Use RAG for facts. |
| Is a JSON-schema response safe to use unvalidated? | No. Validate on receipt. |
| Where does the system prompt live? | Server, versioned. |
| Biggest prompt-injection risk in the UI? | Rendering model output as HTML or loading model-supplied URLs. |
