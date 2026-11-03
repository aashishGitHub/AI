# Evaluate and monitor an AI feature: offline evals, online metrics, tracing and regressions
**Round:** 14 · AI-Powered Frontends · **Level:** Principal · **Time:** 15 min · **Tags:** llm · evaluation · evals
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: a prompt change silently degraded answers and nobody noticed for two weeks. Design evaluation and monitoring.

## What they're really testing
Whether you give non-deterministic features the same discipline as code: versioned prompts, regression gates in CI, production tracing, and flag-based rollouts.

## Core answer (key points)
- **Why it happens:** prompts, models and retrieval change outside normal test coverage; outputs are probabilistic; nobody owns "quality".
- **Offline evals:**
  - Dataset from real, sampled, anonymized queries plus known-hard cases and past incidents.
  - Each case has expected properties, not just one golden string.
  - Scorers: code checks (schema valid, must cite X, must not contain PII/internal hosts, length), model-graded rubrics (spot-checked by humans), periodic human review.
  - **CI gate:** run on every prompt/model/retrieval change; block on regressions beyond a threshold on critical checks; post a diff report on the PR.
- **Online monitoring:**
  - Trace each request: prompt version, model id, retrieved context ids, tool calls, latency, tokens.
  - Explicit signals: thumbs, edits to generated text, regenerate rate.
  - Implicit: suggestion accept/copy rate, task completion after answer, "that's wrong" follow-ups.
  - Safety: flagged outputs, injection detections, rejected tool confirmations.
  - Perf/cost: TTFT, total latency, tokens, errors/429s per model + prompt version.
- **Release practice:** prompts are versioned artifacts; roll out behind flags; shadow (run new prompt silently, compare), A/B, canary; alert on quality-proxy drops per version.
- **Frontend's role:** instrument those UI events, attach `promptVersion` and `modelId` to every event, "report a problem" with consented conversation snapshot, flag-driven prompt A/B.

## Mental model / flow
```
real queries (sampled, anonymized) -> labeled cases {input, checks[]}
   -> run vs (prompt vN, model M) -> scores per check
   -> CI gate + PR diff report
prod: trace(promptVersion, modelId, ctx ids, tokens, latency) + feedback
   -> dashboards per version -> regression alert -> flag rollback
   -> failing prod cases added to eval set
```

## Code sketch
```ts
// Own sketch: eval case shape + a tiny runner
type Check =
  | { kind: 'schema' }
  | { kind: 'cites'; anyOf: string[] }
  | { kind: 'excludes'; patterns: RegExp[] }
  | { kind: 'rubric'; criteria: string; min: number };

interface EvalCase { id: string; input: { question: string; docVersion: string }; checks: Check[] }

async function runSuite(cases: EvalCase[], target: { prompt: string; model: string }) {
  const results = await Promise.all(cases.map(async c => {
    const out = await generate(target, c.input);
    const scores = await Promise.all(c.checks.map(ch => score(ch, out)));
    return { id: c.id, pass: scores.every(s => s.pass), scores };
  }));
  return { passRate: results.filter(r => r.pass).length / results.length, results };
}
```

## Trade-offs & pitfalls
- Model-graded rubrics drift and have biases (e.g. favoring longer answers); calibrate against human labels periodically.
- Small eval sets give noisy pass rates; flag differences smaller than the noise as inconclusive.
- Non-determinism: run multiple samples or low temperature for evals, track variance.
- Logging prompts/outputs means sensitive data: consent, redaction, retention policy.
- Over-indexing on thumbs: most users never click; implicit signals matter more.

## Likely follow-ups
- **How do you triage a regression?** Filter traces by prompt version, diff failing eval cases, check whether retrieval or generation changed, roll back the flag.
- **Who owns evals?** The feature team, like tests; a platform team provides the harness.
- **Shadow vs A/B?** Shadow has zero user impact but only offline-scorable signals; A/B gives real behavioral metrics.
- **Standards for tracing?** OpenTelemetry has GenAI semantic conventions; they are fairly new and evolving, verify current status.

## Say it in 60 seconds
AI features regress silently because prompts, models and retrieval change outside normal tests, so I treat quality like code. Offline, an eval set built from real anonymized queries and past failures, each with expected properties, scored by code checks, model-graded rubrics and periodic human review, runs in CI on every prompt or model change and blocks regressions with a diff report. Online, every request is traced with prompt version, model, retrieved context, tokens and latency, and we watch explicit and implicit feedback, safety signals and cost per version. Prompt changes roll out behind flags via shadow, A/B or canary, with alerts per version, and every production failure becomes a new eval case. The frontend's job is instrumenting those signals and tagging them with prompt and model version.
