# 08 · Rapid fire: the last hour before an interview

Cover the right column, answer the left out loud, uncover. Anything you miss → reread the linked file section.

## LLM basics ([01](01-llm-fundamentals.md))
| Q | A |
|---|---|
| Why stream? | Lower time to first token; total time barely changes. |
| Is the model stateful? | No. History is re-sent each turn. |
| Temperature 0 deterministic? | Not guaranteed on hosted APIs. |
| Context window exceeded? | Trim / summarise / retrieve old turns; show the user it was compacted. |
| Why hallucination? | Trained for plausible text, not verified text. Ground it, cite it, eval it. |
| Embeddings weak at? | Exact tokens: IDs, error codes → hybrid search. |
| Prompt vs RAG vs fine-tune? | Behaviour → prompt; knowledge → RAG; style/narrow task at scale → fine-tune last. |
| Structured output safe? | Validate on receipt anyway (Zod). |
| Reasoning models in UI? | Longer TTFT → visible "thinking" state, cancel, route simple queries to fast models. |

## Streaming and rendering ([02](02-ai-frontend-engineering.md))
| Q | A |
|---|---|
| `EventSource` limits? | GET only, no body, no custom headers → use fetch + stream for chat. |
| Chunk vs event? | Not the same. Buffer, split on blank line, decode with `{ stream: true }`. |
| Proxy kills streaming? | Buffering. `text/event-stream`, `no-cache`, `X-Accel-Buffering: no` (nginx), check compression. |
| Stop button? | `AbortController`; abort ≠ error; keep partial; server cancels upstream on disconnect. |
| Dropped mid-stream? | Short answer: partial + retry. Long task: job + resumable event log (`Last-Event-ID`). |
| Render jank? | rAF batching, memo completed blocks, isolate streaming message, lazy highlight. |
| Auto-scroll? | Only if user is at bottom; else "Jump to latest". |
| Model output as HTML? | Never. Sanitise, no raw HTML, link + image allowlists, CSP. |
| Why block model image URLs? | Data exfiltration via query string on fetch. |
| Citations? | `sources` event first; link only IDs that were sent; permissions filtered before retrieval. |
| Chat state shape? | Messages with ordered `parts` (text/tool/sources) + status; reducer with explicit events. |
| Edit and resend? | Tree with `parentId`; active path; branch switcher. |
| Generative UI safety? | Registry of known components, schema-validated props, no eval, fallback. |
| Approval flow? | Server pauses; card shows real args; server re-checks RBAC on resume; audit; expiry. |
| Screen readers + streaming? | Don't announce tokens; announce start + complete. `role="log"`. |
| Test non-deterministic UI? | Fake provider + MSW streams; evals separate. |

## RAG, agents, evals ([03](03-rag-agents-evals.md))
| Q | A |
|---|---|
| RAG two paths? | Index/write path vs query/read path. |
| Hybrid merge? | Reciprocal Rank Fusion (rank-based, not score-based). |
| Re-ranker? | Cross-encoder on top ~20–50 candidates → keep top few. |
| Wrong answer debug? | Retrieval failure or generation failure? Check retrieved IDs in the trace. |
| Retrieval metric? | recall@k, MRR/nDCG. |
| Generation metric? | Faithfulness, answer relevance, citation accuracy. |
| Embedding model change? | New index side by side, eval both, atomic switch. |
| Agent guardrails? | Max steps, budget, timeouts, allowlist, schema validation, per-user permission, approvals, idempotency, audit, kill switch. |
| Agent eval? | Outcome + trajectory; multiple runs → pass rate. |
| MCP? | Open protocol: servers expose tools, resources, prompts; stdio or Streamable HTTP. |
| MCP risk? | Tool-description injection, changed tools, over-broad tokens, confused deputy. |
| Offline vs online eval? | CI golden set gate vs sampled prod + feedback; prod failures feed the golden set. |
| LLM judge trust? | Specific rubric, reasoning first, cross-family, position randomised, calibrate vs humans. |
| Safe prompt rollout? | Versioned → CI eval → flag → canary → compare by version → ramp/rollback. |
| Semantic cache risk? | Similar ≠ same ("enable"/"disable"), staleness, cross-tenant leaks. |

## Frontend core ([04](04-frontend-core.md))
| Q | A |
|---|---|
| Event loop order? | Task → all microtasks → maybe render (rAF, style, layout, paint) → next task. |
| CWV thresholds (p75)? | LCP ≤ 2.5 s · INP ≤ 200 ms · CLS ≤ 0.1. INP replaced FID March 2024. |
| LCP sub-parts? | TTFB · load delay · load duration · render delay. |
| INP fixes? | Yield long tasks, transitions, workers, virtualise, smaller DOM. |
| Re-render causes? | Own state, parent render, context change. |
| Effects are for? | Syncing with outside systems, not deriving state or handling events. |
| RSC hurts when? | Highly interactive UI, big serialised props, waterfalls, unclear boundaries. |
| Hydration mismatch causes? | Dates/random, browser APIs in render, locale, invalid nesting, extensions. |
| Error boundaries miss? | Event handlers, async, SSR, themselves. |
| State by kind? | Server → Query/RSC · URL → router · form → RHF+Zod · local → useState · global → small store. |
| Token storage? | BFF + httpOnly cookie; PKCE for OAuth in browsers. |
| CORS preflight when? | Non-simple method/headers/content-type (e.g. JSON, Authorization). |
| Why MSW? | Real fetch code runs; mocks at network level. |
| Micro-frontends when? | Many teams needing independent deploys; otherwise modular monorepo. |

## Design ([05](05-system-design.md))
| Q | A |
|---|---|
| First 3 questions? | Actions/risk? Latency type (chat vs inline)? Data sensitivity/tenancy? |
| Always draw? | Browser → BFF (auth, prompt, limits, stream proxy, logs) → model gateway. |
| Long agent runs? | Job model + append-only event log + SSE replay. |
| AI search? | SSR classic results + streamed answer card in parallel; never block results on AI. |
| Inline completion? | Debounce, abort, latest-wins, small model, cache by prefix, acceptance rate metric. |
| Text-to-SQL safety? | Validate SQL/spec server-side, allowlist, read-only, tenant filter, limits; show the query. |
