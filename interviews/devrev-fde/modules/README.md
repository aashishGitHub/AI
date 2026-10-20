# Module guides — every phase, beginner → senior

One guide per module of your work. Inside each module, every **phase** has three rungs:

- 🟢 **Beginner** — a plain-language definition you can say to a new teammate.
- 🟡 **Intermediate** — how it works and how *you* built it, with a real snippet from your repo.
- 🔴 **Senior** — the trade-off, the failure mode, a number you measured, and the boundary of your claim, plus the follow-up the interviewer will ask next.

Every answer is written as complete spoken sentences. Every snippet marked **Source** is an exact copy of the cited
lines in your repos, checked by script; snippets marked **Illustrative** are written for teaching and are labelled as
such. Couchbase monorepo code is never quoted (proprietary) — only described, with local paths.

| # | Module | Phases | Lane |
|---|---|---|---|
| 01 | [Evals & observability](01-evals-and-observability.md) | golden set → deterministic checks → judge → CI gate → agent evals → online eval → honest reporting | [L] (+ [P] Ask AI eval design) |
| 02 | [RAG & vector search](02-rag-and-vector-search.md) | framing → ingest → chunk/embed → index & vector DB → retrieve → ground & generate → cost & model swap | [P] contributor + [L] |
| 03 | [Agents, function calling & MCP](03-agents-and-mcp.md) | tool contracts → MCP → loop → validation → safety → audit → testing | [L] |
| 04 | [Event-driven reliability](04-event-driven-reliability.md) | delivery semantics → idempotency → outbox → CDC → consumers/DLQ → ordering → testing | [L] |
| 05 | [Webhooks & two-way sync](05-webhooks-and-two-way-sync.md) | verify → inbox → mapping → decide → load back → backfill → deletes/DLQ → vendor lessons + AirSync | [L] (+ [P] Workato) |
| 06 | [GraphQL & API design](06-graphql-and-api-design.md) | schema → N+1/DataLoader → keyset cursors → limits/auth → errors → index → partner API | [L] |
| 07 | [SQL & analytics](07-sql-and-analytics.md) | foundations → windows → percentiles/buckets → cohorts → data quality → performance → dashboard | [L] synthetic data |
| 08 | [Serverless, IaC, CI/CD & observability](08-serverless-iac-ci-observability.md) | Lambda → adapter → Terraform → secrets/IAM → CI → observability → containers | [L], never applied to AWS |
| 09 | [Frontend for AI products](09-frontend-ai-ui.md) | streaming → reducer → abort → trust UX → accessibility → performance → testing | [L] |
| 10 | [Agent memory & context](10-agent-memory-and-context.md) | why memory → context window → long-term store → retrieval → memory safety → loop integration → testing | [L] |
| 11 | [Multi-agent orchestration & durable execution](11-multi-agent-orchestration-and-durable-execution.md) | single vs multi-agent → roles/allowlists → patterns → durable execution → retries/budgets → human approval → crash testing | [L] |
| 12 | [Prompt versioning & agent lifecycle](12-prompt-versioning-and-agent-lifecycle.md) | versioned prompts → immutability → pinning → canary/shadow → eval-gated promotion → provenance → honest comparison | [L] |
| 13 | [Java backend via streampulse](13-java-backend-streampulse.md) | structure & architecture rules → modern Java domain → Spring design → Kafka → reliability → testing → concurrency/JVM | [L] |

**How to study a phase (10 minutes):** read the 🟢 question and answer it aloud before reading; do the same for 🟡 and
🔴; then open the linked file and explain the snippet in your own words; finish with the module's self-check.

**Where the rest lives:** the topic ladder across all modules → [`../LEVELS.md`](../LEVELS.md) · deeper follow-ups →
[`../STUDY.md`](../STUDY.md) · behavioural stories → [`../STAR.md`](../STAR.md) · coding drills →
[`../drills/DRILLS.md`](../drills/DRILLS.md).

Honesty rule for every module: say "I built" only for what you wrote; say "I contributed" for Ask AI and other team
work; say "against a mock vendor", "n=5, one model", or "never applied to AWS" whenever those are the facts.
