# 14 · AI-Powered Frontends
> Shipping LLM features that feel fast and stay safe: streaming transport and rendering, structured tool output, trustworthy RAG UX, latency/cost control, and evals · 6 questions · ~1 h 34 min
Source: https://whetstone-v1.vercel.app/#ai-frontend

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Stream an LLM response into the UI: fetch streams, SSE parsing, abort and render batching | Lead / Staff | 20 min | llm · streaming · sse | [notes](01-stream-llm-response-sse-abort.md) |
| 02 | Render streaming Markdown safely: partial syntax, sanitization and code blocks | Lead / Staff | 15 min | markdown · streaming · sanitization | [notes](02-streaming-markdown-safe-rendering.md) |
| 03 | Tool calling and generative UI: render structured outputs and keep a human in the loop | Principal | 20 min | llm · tool calling · generative ui | [notes](03-tool-calling-generative-ui-human-loop.md) |
| 04 | RAG product UX: citations, confidence, empty answers and feedback loops | Lead / Staff | 12 min | rag · citations · ux | [notes](04-rag-ux-citations-trust-feedback.md) |
| 05 | Latency and cost in AI features: caching, streaming, model routing and optimistic UI | Lead / Staff | 12 min | llm · latency · cost | [notes](05-ai-latency-cost-caching-routing.md) |
| 06 | Evaluate and monitor an AI feature: offline evals, online metrics, tracing and regressions | Principal | 15 min | llm · evaluation · evals | [notes](06-evaluate-monitor-ai-feature-evals.md) |

## How these connect
- **Streaming pipeline:** 01 (bytes -> SSE events -> batched state) feeds 02 (incremental, sanitized Markdown). Study them back to back; together they are the "build a chat UI" coding round.
- **Untrusted model output is the common security thread:** 02 (no raw HTML, link/image allowlists), 03 (tool registry, schema validation, confirmation), 04 (permission-filtered sources). All three defend against prompt injection.
- **Quality and trust loop:** 04's feedback and retrieval logs become 06's eval cases; 06's per-version tracing is how you prove 05's cost cuts didn't hurt quality.
- **Ties to round 13:** flags and canary (13-09) and release-tagged observability (13-08) are exactly how prompt versions roll out in 06.
- **Suggested order:** 01 -> 02 -> 03 -> 04 -> 05 -> 06.
