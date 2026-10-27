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
| 14 | [Agent deployment & inter-agent communication](14-agent-deployment-and-inter-agent-communication.md) | agent as a service → deploy topologies/transports → cards & contracts → sync calls (deadlines, retries) → async queue → security across hops → rollout & testing | [L] run locally + in containers, never on a cloud; not A2A |

## Beginner → senior path (three views of every module)

Every module has three files. Use them in this order.

| # | 1. Plain English (start here) | 2. Full guide (🟢 → 🟡 → 🔴) | 3. Real-time scenarios (prove it) |
|---|---|---|---|
| 01 | [simple](simple/01-evals-and-observability.md) | [guide](01-evals-and-observability.md) | [scenarios](scenarios/01-evals-and-observability.md) |
| 02 | [simple](simple/02-rag-and-vector-search.md) | [guide](02-rag-and-vector-search.md) | [scenarios](scenarios/02-rag-and-vector-search.md) |
| 03 | [simple](simple/03-agents-and-mcp.md) | [guide](03-agents-and-mcp.md) | [scenarios](scenarios/03-agents-and-mcp.md) |
| 04 | [simple](simple/04-event-driven-reliability.md) | [guide](04-event-driven-reliability.md) | [scenarios](scenarios/04-event-driven-reliability.md) |
| 05 | [simple](simple/05-webhooks-and-two-way-sync.md) | [guide](05-webhooks-and-two-way-sync.md) | [scenarios](scenarios/05-webhooks-and-two-way-sync.md) |
| 06 | [simple](simple/06-graphql-and-api-design.md) | [guide](06-graphql-and-api-design.md) | [scenarios](scenarios/06-graphql-and-api-design.md) |
| 07 | [simple](simple/07-sql-and-analytics.md) | [guide](07-sql-and-analytics.md) | [scenarios](scenarios/07-sql-and-analytics.md) |
| 08 | [simple](simple/08-serverless-iac-ci-observability.md) | [guide](08-serverless-iac-ci-observability.md) | [scenarios](scenarios/08-serverless-iac-ci-observability.md) |
| 09 | [simple](simple/09-frontend-ai-ui.md) | [guide](09-frontend-ai-ui.md) | [scenarios](scenarios/09-frontend-ai-ui.md) |
| 10 | [simple](simple/10-agent-memory-and-context.md) | [guide](10-agent-memory-and-context.md) | [scenarios](scenarios/10-agent-memory-and-context.md) |
| 11 | [simple](simple/11-multi-agent-orchestration-and-durable-execution.md) | [guide](11-multi-agent-orchestration-and-durable-execution.md) | [scenarios](scenarios/11-multi-agent-orchestration-and-durable-execution.md) |
| 12 | [simple](simple/12-prompt-versioning-and-agent-lifecycle.md) | [guide](12-prompt-versioning-and-agent-lifecycle.md) | [scenarios](scenarios/12-prompt-versioning-and-agent-lifecycle.md) |
| 13 | [simple](simple/13-java-backend-streampulse.md) | [guide](13-java-backend-streampulse.md) | [scenarios](scenarios/13-java-backend-streampulse.md) |
| 14 | [simple](simple/14-agent-deployment-and-inter-agent-communication.md) | [guide](14-agent-deployment-and-inter-agent-communication.md) | [scenarios](scenarios/14-agent-deployment-and-inter-agent-communication.md) |

**The path:**

1. **Beginner:** read the *simple* file for a module, then answer the 🟢 questions in the guide out loud.
2. **Intermediate:** read the 🟡 answers, open the code each one cites, explain it without reading it line by line.
3. **Senior:** the 🔴 answers and every "What not to claim" list; then do the scenarios, asking the clarifying questions first.
4. **Prove it:** run a live mock with [`../MOCK-INTERVIEWER.md`](../MOCK-INTERVIEWER.md), graded by [`../RUBRIC.md`](../RUBRIC.md).

**Suggested order for the agent-focused FDE bar:** 03 → 11 → 14 → 12 → 04 → 05 → 01 → the rest.

**How to study a phase (10 minutes):** read the 🟢 question and answer it aloud before reading; do the same for 🟡 and
🔴; then open the linked file and explain the snippet in your own words; finish with the module's self-check.

**Where the rest lives:** the topic ladder across all modules → [`../LEVELS.md`](../LEVELS.md) · deeper follow-ups →
[`../STUDY.md`](../STUDY.md) · behavioural stories → [`../STAR.md`](../STAR.md) · coding drills →
[`../drills/DRILLS.md`](../drills/DRILLS.md).

Honesty rule for every module: say "I built" only for what you wrote; say "I contributed" for Ask AI and other team
work; say "against a mock vendor", "n=5, one model", or "never applied to AWS" whenever those are the facts.
