# Latency and cost in AI features: caching, streaming, model routing and optimistic UI
**Round:** 14 · AI-Powered Frontends · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** llm · latency · cost
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: feature takes ~8 s and costs more than expected as usage grows. Cut both without hurting answer quality.

## What they're really testing
Separating perceived vs actual latency, knowing the real cost levers (tokens, model size, calls avoided), and measuring quality alongside savings.

## Core answer (key points)
- LLM calls are slow (seconds) and billed per token; both latency and cost scale with model size and prompt/output length.
- **Perceived latency:** stream tokens, show step progress for multi-step work, optimistic UI for the surrounding interaction, do useful work while waiting.
- **Actual latency + cost levers:**
  | Lever | Example |
  |---|---|
  | Don't call | trigger after a pause + min length; require explicit intent for expensive actions; cache "no suggestion" |
  | Route by task | small/fast model for classify/extract/short rewrite; large model for hard reasoning |
  | Prompt caching | reuse a long shared prefix (system prompt, document) across turns |
  | Response caching | key = normalized input + model + prompt version + doc version |
  | Shorter I/O | trim context, concise structured output, per-feature max tokens |
  | Parallelism | independent sub-tasks concurrently; stream the first useful part |
  | Speculation | precompute likely next suggestion while user reads (costs tokens; use carefully) |
- **Frontend specifics:** cancel in-flight requests when input changes (and server stops generation on disconnect); debounce AI triggers more than search (roughly 500-800 ms is a reasonable starting point, tune with data); graceful 429/quota messages with reset time.
- **Server-side:** per-user rate limits and budgets; never trust the client to enforce spend.
- **Measure:** TTFT, total time, tokens per request, cache hit rate, cost per active user, abandonment while waiting, plus quality evals per change.

## Mental model / flow
```
user intent ──▶ [should we call?] ──no──▶ heuristic / cached
                     │yes
                     ▼
              [cache hit?] ──yes──▶ return
                     │no
                     ▼
         [router: task -> model tier] ──▶ provider (prompt-cached prefix) ──▶ stream
                                                    │
                           metrics: TTFT, tokens, cost, quality score
```

## Code sketch
```ts
// Own sketch: cancel stale AI requests as the input changes
function useAiSuggest(input: string) {
  const [s, setS] = useState<string | null>(null);
  useEffect(() => {
    if (input.trim().length < 12) return;            // don't call for tiny inputs
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const r = await fetch('/api/suggest', { method: 'POST', body: JSON.stringify({ input }), signal: ctrl.signal });
        if (r.ok) setS((await r.json()).text);
      } catch { /* aborted or failed; ignore */ }
    }, 600);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [input]);
  return s;
}
```

## Trade-offs & pitfalls
- Semantic caching (matching similar, not identical, questions) can return a wrong answer for a subtly different query; scope it tightly and include versions in the key.
- Cheaper model routing can silently degrade quality; gate with evals and A/B.
- Response caching personalized or permissioned answers across users leaks data.
- Prompt-cache specifics (minimum prefix size, TTL, pricing) are provider-specific and change; verify in current provider docs.
- Optimistic UI for AI output itself is not possible (you don't know the answer); apply it to the surrounding action (message appears sent instantly).

## Likely follow-ups
- **Which metric first?** TTFT for perceived speed; cost per active user for the business.
- **How do you pick the model per task?** Offline eval per tier; pick the cheapest that meets the quality bar.
- **Batching?** For non-interactive bulk work (backfills, summaries), batch APIs are cheaper; not for chat.
- **Abuse?** Per-user budgets and server-side rate limits; cap max tokens per request.

## Say it in 60 seconds
I split perceived from actual latency. Perceived: stream tokens, show progress for multi-step work, keep the UI responsive. Actual latency and cost both scale with tokens and model size, so the levers are: avoid calls with intent and debounce, route easy tasks to a small fast model, use prompt caching for long shared prefixes, cache deterministic responses keyed by input, model and prompt version, trim context and cap output, and parallelize independent steps. On the frontend I cancel stale requests so we don't pay for answers nobody sees, and the server enforces per-user limits. Every change is measured on TTFT, tokens, cost per user and an eval score, so savings never quietly hurt quality.
