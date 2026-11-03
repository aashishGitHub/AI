# Agent Engineer — conversational screen Q&A

> Weighting: **~70% internal agent platforms** (how companies actually run agents: Ramp Glass / Inspect, Sierra Pinecone,
> Stripe Minions, Spotify Honk), **~30% agent engineering craft** (loop, tools, MCP, evals, memory, safety).
> Answers are first-person spoken sentences. Rungs: 🟢 basic · 🟡 working · 🔴 senior (trade-off + failure mode + limit of the claim).

## Read this first: what is verified and what is not

- **Researched on 2026-11-03.** Every platform fact below comes from the source linked next to it (see [Sources](#sources)). Almost all of
  it is **self-reported by the company** in a blog or talk. Say "Ramp says" / "Sierra wrote", never "Ramp has".
- **Numbers drift.** Ramp's Inspect share of merged PRs is ~30% in Ramp's own post (undated), "over half" in Modal's Feb 2026 case
  study, and "three in four" in a secondhand Linear story I could not open. Quote the one you can name, with its date.
- **Not confirmed by a primary source:** that Glass is built on the Claude Agent SDK (only a third-party explainer says so), and
  that Spotify Honk uses Claude Code / Agent SDK (Spotify's Part 1 does not name the harness). Do not state either as fact.
- **Your evidence** is in this repo: [`agent-lab/`](../../agent-lab/NOTES.md) (MCP agent, approval gate, audit, trajectory evals, mesh)
  and the craft modules under [`devrev-fde/modules/`](../devrev-fde/modules/README.md). Say "I built" only for that.

---

## 1. The mental model: an internal agent platform is seven layers

When they ask "how would you build Glass / Pinecone here", walk these layers top to bottom. Every real platform below maps onto them.

| # | Layer | Job | Ramp | Sierra Pinecone | Stripe Minions | Spotify Honk |
|---|---|---|---|---|---|---|
| 1 | **Surfaces** | Meet people where they already work | Slack, web, mobile, Chrome extension (Inspect); Glass app | Browser, Slack, Linear, phone | Slack thread tag, docs/flags/ticket UIs, CI "fix flaky test" button | Slack, GitHub Enterprise via MCP |
| 2 | **Router / intent classifier** | Pick repo, env, model, budget so users don't | Slack classifier picks repo (with an "unknown" option); Ramp Router picks model | Classifier picks repo, env, harness, model, reasoning budget | — (engineer scopes the task) | Interactive agent gathers requirements, hands a prompt to coding agent |
| 3 | **Session + durable state** | A unit of work that streams, survives crashes, can be shared | Cloudflare Durable Object per session, own SQLite, WebSocket stream | "Agency": K8s pod per runner, Redis Streams live, durable events + checkpoints; resume and branch | Web UI to watch a run | Logs to GCP, traces in MLflow |
| 4 | **Sandbox / environment** | Full dev env, isolated, fast to start | Modal sandbox, full stack (Postgres, Redis, Temporal, RabbitMQ), image rebuilt + snapshotted every 30 min | Pod with repo, warm build cache, sidecars, hot-reload servers, ~1 s setup | Pre-warmed devbox (~10 s), no prod, no internet | Fleet Management runs the change across repos |
| 5 | **Harness** | The agent loop itself | OpenCode (server-first, typed SDK, plugins) | Codex **and** Claude Code behind an AG-UI-based adapter | Fork of Block's Goose, agent steps interleaved with deterministic git/lint/test steps | Internal CLI that hides which agent/LLM is used |
| 6 | **Tools + knowledge** | What the agent can touch and know | Sentry, Datadog, LaunchDarkly, Braintrust, GitHub, Slack, Buildkite; Glass: Linear, Notion, Google, Slack, Gong + shared **Skills** | Slack, Linear, GitHub, email; **Skills** (private/shared/default), **Projects** with shared context; per-user MCP auth | **Toolshed**: one central MCP server, 400+ tools, small default subset per agent; shared rule files | Local MCP for format/lint |
| 7 | **Governance** | Creds, cost, review, audit, eval | GitHub App token per clone; PR opened with *user's* token so they can't self-approve; cost meter per project | Network proxy injects creds, agent never holds them; central cost team; no token leaderboards | Human review on every PR; max 2 CI rounds | LLM-as-judge on diffs; same PR review/merge pipeline |

**One line to say:** "Every one of these converged on the same shape: a cloud sandbox per session, one central tool gateway, a router
so users don't choose infra, durable sessions you can share, and the existing review pipeline as the safety net."

---

## 2. Platform teardowns

### 2.1 Ramp — Inspect (background coding agent) and Glass (AI workspace)

**Inspect, under the hood** (Ramp builders blog; Modal case study)
- Each session = a Modal sandbox VM with the full stack. Per-repo images rebuilt and snapshotted **every 30 minutes**, so code is at
  most 30 min stale. Sandbox is warmed **while the user is still typing**; the agent may *read* before git sync finishes, but an
  OpenCode plugin **blocks edits** until sync completes.
- State: one Cloudflare Durable Object per session with its own SQLite → sessions can't interfere; streaming over WebSockets.
- Git: GitHub App installation token per clone; commits carry the user's git config; the **API opens the PR with the user's own
  token** so the requester cannot approve their own change. Webhook tracks PR status.
- Verification: backend runs tests, reads telemetry, checks feature flags; frontend takes before/after screenshots, live previews,
  computer use in a streamed desktop.
- Multiplayer: many people in one session, every prompt attributed. Data model must not bind a session to one author.
- Follow-up prompts are **queued**, not injected mid-run; there is an explicit stop control.
- Chrome extension sends **DOM + React internals instead of screenshots** to save tokens; force-installed via device policy.
- Scale: passed **1 million sessions** (dbt Summit talk, write-up dated 2026-10-27).

**Glass** (Eric Glyman launch post, 2026-10-13; dbt Summit talk)
- Trigger: Ramp spent **$1.5M on tokens in one week in May 2026**. Glass is the answer to "everyone has tools, nobody shares what works".
- Core idea: "learn things once". Saved prompts/workflows become **Skills** that anyone starts from; sessions are multiplayer (a support
  agent pulls an engineer into her session to finish a ticket).
- Every request goes through **Ramp Router** (model selection); Ramp says moving onto it cut its own bill **30%**.
- Cost meter per project with limits set up front.
- Example: one account manager's saved skill took captured feature requests from ~300/month (hand-copied into Salesforce) to
  ~20,000/month. 323 employees had made 6,500+ edits to what Glass knows (as of launch).
- Pre-installed on new hires' laptops, pre-connected; spread organically, especially to sales and other non-engineers.
- Opened to outside companies in early access on 2026-10-13.

**Ramp's other pieces** (dbt talk): *Ramp Research* (data agent, query volume now exceeds human-written queries), *Rampplify*
(internal app hosting, ship and tear down fast), *WaveDash* (dashboards as SQL files in a repo → agents edit them like code; migrating
off Looker).

**What Ramp admits is not solved:** ROI measured by "black boxes and vibes"; AI-written docs bloating the wiki; legacy BI still in use.

### 2.2 Sierra — Pinecone (internal cloud agent)

Source: "Pinecone: harnessing the wisdom of the workforce", Allen Chen & Tess Rosania, 2026-07-15. (Not the vector DB company.)

- **Starting point (Jan 2026):** every engineer had Codex, Claude Code and Cursor on the laptop. Laptop agents didn't scale and
  improvements stayed with one person.
- **One agent, not many bots.** A classifier reads the prompt and picks repo, environment, harness, model and reasoning budget.
  Non-technical users could not answer "8 CPUs or 0.1?", so the platform stopped asking.
- **Architecture:** *App server* (UI, API, persistence, integrations, fan-out stream to every open tab) → *Agency* (reconciles each
  runner into a Kubernetes pod, Redis Streams for live traffic, durable events + checkpoints stored separately) → *Runner* (a Go
  supervisor process that runs Codex or Claude Code, manages dev services, brokers privileged operations).
- **Harness-agnostic:** both harnesses wrapped in one adapter on an **AG-UI**-based protocol → swap providers without touching UI.
- **Durable sessions:** a replacement runner resumes where the dead one stopped; sessions last hours or days; **branching** reuses
  the same checkpoint mechanism.
- **Security:** harness has limited network + filesystem. A **network proxy** approves/rejects each outbound call and **injects
  credentials**, so the agent never sees a real secret. "Assume it can do everything; trust nothing." Per-user MCP auth on branch.
- **Plugs in:** Slack, Linear, GitHub (opens PRs, watches CI, answers review comments, fixes failing tests, rebases, pings a human
  only when judgment is needed), email, webhooks/schedules, other internal tools (incident management, code review, Q&A bots) that
  create sessions; Skills; Projects (sessions share context and message each other); shareable live previews.
- **Numbers (self-reported, month before July 2026):** 600 people, 75,000+ sessions, 96% of engineering uses it, **70% of PRs opened
  through Pinecone**, usage tripled monthly since April while cost fell.
- **What worked:** cloud over laptops; **primitives over workflows** (workflows got rewritten every model upgrade, primitives —
  context, environments, company tools — held); meeting users in ChatGPT/Claude/Linear/GitHub; an enthusiast alpha cohort who became
  champions; central cost team; **no token leaderboards**.
- **What was hard:** "an agent is only as useful as the environment you give it" — per-role tools/data/permissions assembled on the
  fly without weakening security; no vendor fit, so they built it; harness misbehaviour (wrong config, missed AGENTS.md, wasteful
  approaches) — but because it's central, one fix lands for everyone. Same infra now powers *Ghostwriter*, their customer-facing builder.

### 2.3 Stripe — Minions (one-shot unattended coding agents)

Source: Alistair Gray, stripe.dev, Part 1 2026-02-09 (Part 2 2026-02-19).

- Unattended, one-shot: minions write all the code, humans review. **1,000+ merged PRs/week** (Part 1); Part 2 coverage says 1,300+.
- **Devbox** = the same machine engineers use, pre-warmed, ~10 s, isolated from prod and internet → no permission prompts needed.
- Harness: fork of Block's **Goose**, orchestration **interleaves agent steps with deterministic code** (git, lint, tests). This is
  the "blueprint" idea: don't let the LLM do what a script does reliably.
- **Toolshed:** one central MCP server, 400+ tools. Each agent gets a **small default subset**, not all 400. Before the run, relevant
  tools run deterministically over likely links to **pre-load context**.
- Rule files shared with Cursor / Claude Code, applied **per subdirectory**, not globally.
- Feedback: lint on every push (<5 s), CI on push with autofix, **max 2 CI rounds** (cost + diminishing returns), then hand to a human.
- Thesis: "if it's good for humans, it's good for LLMs". Shift feedback left.

### 2.4 Spotify — Honk (background agent inside Fleet Management)

Source: Charas & Bruggmann, Spotify Engineering, 2025-11-06 (Part 1 of 4).

- Fleet Management already applied changes across thousands of repos with **deterministic scripts**. Honk replaces only the
  *transformation* step with an agent. Targeting, PR creation, review, merge unchanged.
- Why: deterministic hit a wall — one Maven dependency updater grew past **20,000 lines** of edge cases.
- Internal CLI delegates to an agent, runs format/lint via local MCP, **LLM-as-judge on the diff**, logs to GCP, traces in MLflow.
  CLI hides which agent/LLM → they can switch.
- Reported: 1,500+ merged agent PRs, Fleet Management overall ~half of Spotify's PRs since mid-2024, 60–90% time saved on migrations.
- Open problems they name: slow, unpredictable output, guardrails/sandboxing, cost. Parts 2–3 cover context engineering and feedback loops.

### 2.5 The counter-example — Klarna customer service (what did not work)

- Feb 2024: Klarna said its assistant did the work of ~700 agents and handled ~2/3–3/4 of chats (company claim; figures vary by report).
- May 2025 (Bloomberg interview, widely re-reported): CEO said cost had been "a too predominant evaluation factor" and quality
  suffered; Klarna started hiring humans again for a hybrid model.
- **Lesson to say:** optimise a customer-facing agent on cost/deflection alone and quality falls; you need a quality metric and an
  easy path to a human from day one. Contrast: the internal platforms above keep the human review step and measure merged work.

---

## 3. Worked vs did not work — the pattern table

| Worked (seen in 2+ platforms) | Did not work / still open |
|---|---|
| Cloud sandbox per session, not laptop agents (Ramp, Sierra, Stripe) | Laptop-only agents: no sharing, no central fix, no governance (Sierra) |
| Pre-warmed / snapshotted envs: seconds to start (Ramp 30-min snapshots, Sierra ~1 s, Stripe ~10 s) | Making users choose CPU / repo / model (Sierra) |
| Router/classifier picks repo, model, budget (Ramp, Sierra) | Many single-purpose bots → consolidated into one agent (Sierra) |
| One central tool gateway (Stripe Toolshed, Sierra proxy/MCP) with **small default tool sets** | Hand-built workflows → rewritten every model upgrade; build primitives instead (Sierra) |
| Credentials injected by a proxy / scoped tokens, never in the agent (Sierra, Ramp) | ROI measurement: "black boxes and vibes" (Ramp) |
| Reuse the existing human PR review + CI as the safety net (all four) | Token spend explosion without a meter ($1.5M/week, Ramp) |
| Deterministic steps interleaved with agent steps (Stripe, Spotify) | Unbounded CI retry loops → cap at 2 (Stripe) |
| Shared Skills / rule files so one person's win becomes the default (Ramp, Sierra, Stripe) | AI-written doc bloat (Ramp) |
| Multiplayer, shareable sessions (Ramp, Sierra) | Cost-only success metric on customer-facing agents (Klarna) |
| Harness/model-agnostic adapter (Sierra AG-UI, Spotify CLI, Ramp Router) | Single-vendor lock-in (explicitly avoided by Ramp) |
| Organic adoption via a champion cohort, not a mandate (Ramp, Sierra) | Leaderboards of token usage (Sierra avoids them) |

---

## 4. Conversational Q&A — platform band (the 70%)

### 🟢 Q1. "What is an internal agent platform, and why do companies build one instead of giving everyone Cursor?"
**A:** An internal agent platform is the shared layer that runs agents in the cloud for the whole company: a sandbox per task, a
central set of tools with the right credentials, a router that picks model and environment, and sessions people can watch and share.
Companies build it because laptop tools give you individual speed but no compounding. Sierra wrote exactly this: in January every
engineer had Codex, Claude Code and Cursor, but improvements stayed with one person. Once the agent runs centrally, one fix to the
harness or one good skill lands for everyone, cost is visible, and security can enforce one policy at one choke point.

### 🟢 Q2. "Walk me through what happens when someone at Ramp asks Inspect for a change in Slack."
**A:** A fast classifier reads the message, the thread and the channel name and picks the repo, with an explicit "unknown" option so
it can ask instead of guessing. The platform starts a Modal sandbox from a snapshot of that repo that is at most thirty minutes old,
and it starts warming while the person is still typing. The agent, OpenCode, can read files immediately but a plugin blocks edits until
git sync finishes, so it never edits stale code. Session state lives in a Durable Object with its own SQLite and streams to Slack and
the web UI. The agent runs tests, checks telemetry and flags, takes screenshots for UI work, pushes a branch, and then the API opens
the PR with the requester's own GitHub token, so they cannot approve their own change. Normal review and CI do the rest.

### 🟡 Q3. "Pinecone and Glass both claim to 'capture the wisdom of the workforce'. What does that actually mean technically?"
**A:** Three concrete mechanisms. First, **Skills**: a saved, versioned prompt-plus-tools playbook that can be private, shared, or on
by default; Ramp's example is one account manager's feature-request skill going from about 300 to about 20,000 captured requests a
month. Second, **shared sessions and projects**: sessions are readable and joinable, and in Pinecone sessions in a project share
searchable context and can message each other. Third, **central harness fixes**: because every run is in one platform, the team sees
misbehaviour like missed AGENTS.md files and fixes it once. The honest limit: none of the posts show a measurement that the captured
knowledge stays correct over time; Ramp itself complains about AI-generated doc bloat. I'd want ownership and expiry on skills.

### 🟡 Q4. "Why did Sierra go to one agent with a classifier instead of a menu of specialised bots?"
**A:** Because users were bad at picking, and the bots fragmented knowledge. Non-technical people couldn't say whether a task needed
eight CPUs or a tenth of one, or which repo it lived in. A classifier choosing repo, environment, harness, model and reasoning budget
moves that decision to the platform, where it can be measured and tuned. The trade-off is that a wrong route is now invisible to the
user, so the classifier needs an "unknown, ask me" path like Ramp's, logging of every route decision, and an eval set of real prompts
labelled with the right route.

### 🟡 Q5. "How do these platforms handle credentials and permissions?"
**A:** The pattern is: the agent never holds a real secret. Sierra runs the harness with limited network and filesystem and sends
every outbound call through a proxy that approves or rejects it and injects the credential. Ramp mints a GitHub App installation token
per clone and opens PRs with the user's token. Stripe goes the other way on isolation: devboxes have no prod and no internet, so the
agent can run without permission prompts. The principle I'd state is "assume it can do everything, trust nothing": scope by
environment and by a proxy, not by asking the model to behave. The open question is per-user identity — the agent should act with the
requester's permissions, not a superuser service account, and Sierra mentions per-user MCP authorization for that.

### 🟡 Q6. "What is Stripe's Toolshed and why does 'small default tool set' matter?"
**A:** Toolshed is Stripe's single central MCP server with over 400 tools for internal systems and SaaS. The important detail is that a
minion does not get all 400: it gets a small default subset and can request more. Every tool definition costs context tokens and adds
a wrong choice the model can make, so tool selection accuracy drops as the list grows. Stripe also runs some tools deterministically
before the agent starts, to pre-load context from links in the task. So the gateway centralises auth, audit and ownership, and
per-task curation keeps the model's choice small.

### 🟡 Q7. "Why interleave deterministic steps with agent steps?"
**A:** Because git operations, lint and test runs have one right way to do them, and an LLM doing them adds cost and a failure mode for
nothing. Stripe's harness runs those as code between agent steps; Spotify kept targeting, PR creation, review and merge deterministic
and swapped only the transformation step for an agent. The rule I use: the LLM decides, code executes anything with a fixed procedure.
It also makes runs easier to test, because the deterministic parts have normal unit tests.

### 🔴 Q8. "Design an internal agent platform for a 1,000-person company. Where do you start?"
**A:** I start with one high-volume job that already has a review gate, because that gives me a safety net and a metric. Background
coding PRs are the obvious one: success is "merged without human-written code", and the existing PR review catches mistakes. Then I
build the seven layers thinly: Slack plus web as surfaces; a classifier for repo and model with an "unknown" path; a session service
with durable, append-only events so a crashed runner resumes and sessions can be shared; snapshotted sandboxes so start is seconds;
a harness behind an adapter so I can swap Claude Code, Codex or OpenCode; one tool gateway over MCP with per-user scoped auth and a
credential-injecting proxy; and governance from day one — per-project cost meter, a cap on CI rounds, audit of every tool call. I'd
grow through a champion cohort, not a mandate. Failure modes I'd plan for: snapshot staleness causing bad diffs, token spend
explosion, and skills rotting. The limit: everything I know of this shape is from company blogs, which report wins, not failures.

### 🔴 Q9. "How would you measure whether the platform is worth it?"
**A:** Ramp's data engineer said they measure ROI by "black boxes and vibes", so this is genuinely unsolved and I'd say that. I'd
separate output from outcome. Output: sessions, merged PRs per week with no human-written code (Stripe's metric), share of PRs opened
through the platform (Sierra's 70%), time-to-first-diff. Quality: revert rate and follow-up-fix rate of agent PRs versus human PRs,
review time per PR, CI rounds per task. Cost: tokens and compute per merged PR, which is the number that catches a $1.5M week early.
And for non-code work like Glass skills, adoption of a skill by people other than its author. I would not use token usage as a
leaderboard — Sierra explicitly avoids that because it rewards waste.

### 🔴 Q10. "What breaks first when this scales from 50 to 600 users?"
**A:** Three things, from the posts and from general distributed-systems sense. Cost: usage tripled monthly at Sierra, and Ramp had a
$1.5M token week, so you need routing to cheaper models and hard per-project limits. Environments: every new team needs different
tools, data and permissions, and Sierra calls this the hard part. And review load: if agents open 70% of PRs, human reviewers become the
bottleneck, which is why Pinecone answers review comments and fixes CI itself and only pings a human for judgment. Session durability
also matters more: long sessions on preemptible pods need checkpoint-and-resume, which Sierra built into Agency.

### 🔴 Q11. "Build vs buy — Devin, Cursor background agents, Codex cloud. Why did Ramp and Sierra build?"
**A:** Both say no vendor met their requirements, and Ramp's argument is that owning the tooling lets the agent have the same context
and tools as an engineer — Sentry, Datadog, LaunchDarkly, Buildkite — which a vendor can't wire for you. Both also deliberately stay
model- and harness-agnostic. My honest view: building makes sense when you have a platform team, a large codebase, and internal tools a
vendor can't reach; for a small team, buy the harness and build only the tool gateway and the environment snapshots, because those are
where the company-specific value is. Note that Sierra and Ramp both built on top of existing harnesses — Codex, Claude Code, OpenCode —
they did not write their own agent loop.

### 🔴 Q12. "What would you not let an internal agent do?"
**A:** Anything irreversible outside a review gate: merge its own PR, deploy to prod, send external email or payments, or change
permissions. Ramp enforces the first structurally by opening PRs with the requester's token. Stripe enforces isolation by giving devboxes
no prod and no internet. Everything that reads untrusted content — Slack threads, tickets, web pages — is a prompt-injection channel, so
the agent's write tools should be gated by policy at the proxy, not by the prompt. In my agent-lab the write tools go through an approval
gate that defaults to deny, and every call is audited.

### 🟡 Q13. "Why do sessions need to be durable and multiplayer?"
**A:** Durable because agent runs last minutes to days and pods die; Sierra records every event so a replacement runner resumes and the
same checkpoints give you branching for free. Multiplayer because the value is in handoffs: a support person starts a session, pulls in an
engineer, and the engineer sees the full context instead of a summary. Ramp's design note is that the data model must not tie a session to
one author and every prompt must be attributed. And follow-up prompts should queue rather than interrupt a running step.

### 🟡 Q14. "How do non-engineers use these platforms?"
**A:** Mostly through Skills and Slack, not code. Ramp's Glass spread to sales and account managers: one saved skill pulls feature requests
from Gong calls, another emails customers when the feature ships. Sierra's automations scan email and Slack each morning and produce
action-item lists. Ramp's Chrome extension lets people describe UI changes on a live React app. The platform's job is to hide infra choices
and keep a cost meter visible.

### 🔴 Q15. "What's the failure story you'd watch for in a customer-facing agent versus an internal one?"
**A:** Internal agents have a human reviewer and an existing pipeline behind them, so a bad output costs review time. A customer-facing
agent's bad output reaches the customer directly. Klarna is the public example: they optimised for cost, quality fell, and in 2025 the CEO
said cost had been too dominant a factor and they began hiring humans back. So for customer-facing agents I'd require a quality metric
alongside deflection, policy-following tests — Sierra's τ-bench measures that and introduced pass^k, which is all k runs succeeding — and a
cheap path to a human.

---

## 5. Craft band (the 30%) — short answers, deep links

| Topic | Say this | Deep dive in this repo |
|---|---|---|
| Agent loop | "A loop: model proposes a tool call, code validates args against the schema, executes with a timeout, returns a result the model can read even on error, repeat until final answer or max steps." | [03-agents-and-mcp](../devrev-fde/modules/03-agents-and-mcp.md) Phase 3–4, `agent-lab/agent/loop.py` |
| Tool design | "Tool descriptions are prompts. Fewer, well-named tools with typed args beat many overlapping ones — Stripe gives a small default set out of 400." | 03 Phase 1 |
| MCP | "A protocol so tools are written once and any harness can call them; it moves auth, audit and ownership to a server. It doesn't solve tool selection or permissions by itself." | 03 Phase 2, `agent-lab/mcp_server/` |
| Safety | "Default-deny write tools, approval gate, grounded-argument check, treat tool output as untrusted data, enforce at the proxy not the prompt." | 03 Phase 5, `agent-lab/agent/approval.py`, `grounding.py` |
| Evals | "Grade the trajectory — which tools, which args, what changed — not just the final text. Golden + held-out cases, pass@k for capability, pass^k for reliability." | [llm-eval-and-observability](../llm-eval-and-observability/README.md), `agent-lab/evals/` |
| Context & memory | "Context is a budget. Pre-load what's deterministic, retrieve the rest, compact long sessions, keep long-term memory as explicit, owned records." | [10-agent-memory-and-context](../devrev-fde/modules/10-agent-memory-and-context.md) |
| Multi-agent / durable | "Prefer one agent with good tools; split only when contexts truly differ. Durable execution means checkpointed steps and idempotent writes." | [11-multi-agent-orchestration](../devrev-fde/modules/11-multi-agent-orchestration-and-durable-execution.md) |
| Prompt lifecycle | "Prompts are versioned artifacts with evals in CI, canary by percentage, stop on any safety failure." | [12-prompt-versioning](../devrev-fde/modules/12-prompt-versioning-and-agent-lifecycle.md) |
| Agent services | "Agents as HTTP services with signed envelopes and a leased queue; not the A2A protocol." | [14-agent-deployment](../devrev-fde/modules/14-agent-deployment-and-inter-agent-communication.md), `agent-lab/mesh/` |
| Frontend for agents | "Stream events, show tool calls and diffs, let users interrupt, queue follow-ups." | [09-frontend-ai-ui](../devrev-fde/modules/09-frontend-ai-ui.md), `fe-hands-on/app/agent-console-ui` |

### 🟡 C1. "Your agent works in the demo and fails 30% in production. What do you do?"
**A:** I stop changing prompts and build the eval first. I pull real failing traces, label what the right trajectory was, and turn them
into cases next to the passing ones. Then I classify failures: wrong tool, wrong args, missing context, or the environment lied. Most
production failures in my experience and in these blogs are context and environment, not model — Sierra's "an agent is only as useful as
the environment you give it". I fix the biggest bucket, re-run the whole set including held-out cases, and only ship when it doesn't
regress. In agent-lab I did exactly this for two live failures and kept four held-out cases to catch over-fitting.

### 🔴 C2. "Pass@k vs pass^k — which one do you report?"
**A:** Pass@k is "at least one of k tries succeeds" — a capability ceiling, fine when a human picks the best. Pass^k is "all k succeed" —
reliability, which is what an unattended agent needs. Sierra's τ-bench introduced pass^k because agents that look fine on one try fall
apart on repeats. For an internal background agent with review, I'd report pass^1 and pass^3; for customer-facing, pass^k with k at least 4.

### 🔴 C3. "How do you keep an agent from looping and burning tokens?"
**A:** Hard caps owned by code, not the model: max steps, max CI rounds — Stripe uses two — a token budget per session, and a wall-clock
timeout. Plus a cost meter the user can see, like Glass. And detect repeated identical tool calls and stop with a clear message.

### 🟡 C4. "Prompt injection through a Slack thread or ticket — how do you defend?"
**A:** You can't make the model immune, so limit what an injected instruction can do. Mark tool output as untrusted data, keep write tools
behind approval or a policy proxy, scope credentials to the requester, isolate the sandbox network like Stripe's devboxes, and require a
grounded argument — a write's target must come from the user's request, not from retrieved text. That last one is in agent-lab's
`grounding.py`.

---

## 6. Your positioning (say it in 60 seconds)

"I'm a front-end and platform architect with ten-plus years, now focused on agents. I've built an MCP-based agent with an approval gate,
audit log and a trajectory eval harness, and agent services that talk over signed envelopes. What draws me to agent engineering is the
platform shape the strongest teams converged on — Ramp's Inspect and Glass, Sierra's Pinecone, Stripe's Minions: cloud sandboxes, one tool
gateway, a router, durable shareable sessions. That's distributed systems plus UX, which is where I've spent my career. The UI half —
streaming sessions, multiplayer, letting people interrupt and review — is exactly the front-end work most agent teams under-invest in."

**Honest gaps (say them before they find them):** I have not run an agent platform for hundreds of users; my evals are small-n on one
model; I haven't operated Modal or Durable Objects in production — I know them from the published designs.

---

## 7. Questions to ask them

1. "Which job did your platform win first, and what is the success metric for it — merged PRs, sessions, something else?"
2. "Is the agent acting with the requester's identity or a service account? Where is policy enforced?"
3. "How do you decide which harness and model run a task — router, user choice, or fixed?"
4. "What's your current biggest failure bucket: environment, context, tool selection, or review load?"
5. "How do you keep shared skills or rules from going stale?"
6. "How do you measure ROI today?" (Ramp's own answer was "vibes" — listen for whether they have better.)

---

## 8. Drill: one-line answers (cover the right column)

| Prompt | One line |
|---|---|
| Why cloud, not laptop agents? | Sharing, central fixes, governance, cost visibility. |
| Snapshot every 30 min — why? | Seconds to start; at most 30 min stale; edits blocked until sync. |
| PR with requester's token — why? | So nobody approves their own agent's change. |
| Credential proxy — why? | The agent never sees a secret; policy at one choke point. |
| Small tool subsets — why? | Context cost and selection accuracy degrade with tool count. |
| Cap CI rounds at 2 — why? | Diminishing returns; cost and time. |
| Primitives over workflows — why? | Workflows get rewritten every model upgrade; context, envs and tools last. |
| Harness adapter — why? | Swap Codex / Claude Code / OpenCode without touching the product. |
| What's unsolved? | ROI measurement, review load, skill rot, cost spikes. |

---

## Sources

Primary (company-authored):
- Sierra — [Pinecone: harnessing the wisdom of the workforce](https://sierra.ai/blog/pinecone-harnessing-the-wisdom-of-the-workforce) (2026-07-15)
- Sierra — [τ-Bench: Benchmarking AI agents for the real world](https://sierra.ai/blog/benchmarking-ai-agents)
- Ramp — [Introducing Glass](https://ramp.com/blog/introducing-glass) (2026-10-13)
- Ramp — [Why we built our background agent](https://builders.ramp.com/post/why-we-built-our-background-agent) (undated on page)
- Stripe — [Minions: Stripe's one-shot, end-to-end coding agents](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) (2026-02-09)
- Spotify — [1,500+ PRs later: Honk, Part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) (2025-11-06)

Secondary (vendor / press — weaker):
- Modal — [How Ramp built a full-context background coding agent on Modal](https://modal.com/blog/how-ramp-built-a-full-context-background-coding-agent-on-modal)
- dbt — [Ramp's internal AI agents: a million sessions](https://www.getdbt.com/blog/ramp-internal-ai-agents-million-sessions) (2026-10-27, summary of a dbt Summit talk)
- ZenML LLMOps DB — [Building an internal cloud agent platform (Sierra)](https://www.zenml.io/llmops-database/building-an-internal-cloud-agent-platform-to-scale-organizational-knowledge)
- Entrepreneur — [Klarna is hiring customer service agents again](https://www.entrepreneur.com/business-news/klarna-ceo-reverses-course-by-hiring-more-humans-not-ai/491396) (May 2025, from a Bloomberg interview)
- BuildBetter — [What is Ramp Glass?](https://blog.buildbetter.ai/what-is-ramp-glass/) (only source for the Claude Agent SDK claim — unverified)
