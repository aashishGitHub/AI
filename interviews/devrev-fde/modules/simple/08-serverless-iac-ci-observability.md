# Module 08 in plain English: Serverless, IaC, CI/CD and observability

> **Read this first**
> - **What it is for:** learning serverless, Terraform, CI/CD, containers and observability, matching the job-description lines "hands-on deployment experience on serverless or edge platforms, plus CI/CD, containers, and observability practices" and "logging, error surfacing, and telemetry".
> - **Who it is for:** a beginner. No repo knowledge needed.
> - **Full module:** [08-serverless-iac-ci-observability.md](../08-serverless-iac-ci-observability.md). Read it after this file.

**Honesty lanes.** [P] = shipped at Couchbase. [L] = my own build. [K] = knowledge only.

- Everything here is **[L]**, my own work.
- **Nothing was ever applied to a real AWS account.** Terraform was only validated (Terraform 1.14.2 locally).
- streampulse's `envs/local` was applied only against the moto emulator (a fake AWS for local testing).
- The code lives in three of my builds:
  - [offline-sync-app](../../../../../GolangExercise/offline-sync-app/) (FieldSync: Go Lambdas plus Terraform).
  - [ticket-booking](../../../../../GolangExercise/ticket-booking/) (more Lambdas, a Terraform observability module).
  - [streampulse](../../../../../streampulse/) (Terraform against emulators, a Spring Cloud Function, a Prometheus and OpenTelemetry stack, a Dockerfile).
- The agent-eval workflows and the `/healthz` handler live in this repo: [agent-eval.yml](../../../../.github/workflows/agent-eval.yml), [eval-gate.yml](../../../../.github/workflows/eval-gate.yml) and [stream.go](../../../../fe-hands-on/server/stream.go).
- AWS limits (15 minute timeout, memory range, concurrency quota, API Gateway timeout, SQS visibility guidance): **verify in the current AWS docs before quoting.**

---

## Phase 1: Serverless fundamentals (handler model, cold starts, time and memory limits, concurrency)

**Analogy: a taxi rank vs owning a car.** With Lambda you do not own the car. You call a taxi for each trip. You pay per trip. But the taxi may take a minute to arrive the first time.

### What a Lambda function is

- A Lambda function is a handler that AWS runs once per event.
- AWS decides how many copies of my code run at any moment.
- I do not manage a machine or a listening port.
- The unit I write is "one event in, one result out".
- My Lambdas are Go binaries built for `provided.al2023` on arm64. The binary must be named `bootstrap`.
- The trade: I give up long-lived process state. In return I get no server management and scaling per request.
- None of mine was ever deployed to a real account. I describe this from the design and the Terraform, not from production traffic.

### Cold starts

- A cold start is the extra time when AWS must create a fresh execution environment before the handler can run.
- In that start-up phase my package-level code, `init()` and `main()` run until they call `lambda.Start`.
- After that the same environment can serve many calls. Those are called warm.
- I have not measured a single cold start. Nothing ran on AWS. I would never quote a number for my functions.

### Where to put expensive setup

- Put it in start-up code, outside the per-request handler. A warm environment reuses it.
- In `server-lambda` the database pool is built once in `init()`. The handler only calls the adapter.
- There is a deliberate comment: no `defer Close()`. A warm environment is reused. Closing the pool after the first request would defeat pooling.
- Failure mode: `log.Fatalf` in `init()` kills the environment at start-up.
- A bad config then shows up as a failed cold start on every new environment, not as a clean 500.
- Two phases: `init()` is paid once per environment. `handler` is the only code paid per request.

### Scheduled Lambdas open and close a pool per call

- `saga-worker-lambda` is a scheduled catch-up job. It runs rarely and briefly.
- So a pool that lives for one invocation is simple and leaks nothing.
- The API Lambda serves bursts, so a warm pool matters there.
- The cost: one fresh connection setup per run. I expect it is small. I did not time it.
- Say "one-shot job, one-shot pool". If pushed: I chose by reasoning, not by measurement.

### Memory, timeout and concurrency together

- They are one decision. Lambda gives CPU in proportion to memory. Every concurrent execution holds its own database connections.
- In `ticket-booking` the API function has 512 MB, a 15 second timeout and reserved concurrency of 50.
- Reserved concurrency (a cap on how many copies can run at once) bounds how many pgx connections that function can open against RDS Proxy.
- The trade-off: it protects the database. It also turns a traffic spike into throttled requests instead of a slow database.
- That is the right failure for a seat-booking write path. I would argue for each function separately.
- What breaks first is the database connection budget, not the function. A stuck handler is capped by the timeout.
- The number 50 is a design choice. I never load-tested on AWS. The only claim is that the cap is wired and validated in HCL.

### SQS visibility timeout vs function timeout

- Question: why is a 30 second SQS visibility timeout with a 30 second function timeout a problem?
- A message can become visible again while the first attempt still runs. That causes a duplicate delivery and extra load.
- In my eventing module both are 30 seconds.
- I recall AWS guidance that the queue visibility timeout should be several times the function timeout. Verify the exact multiple in the current docs.
- My consumers are safe because `sqsconsume` checks a `processed_events` table before calling the handler. A duplicate becomes a no-op.
- I would still raise the visibility timeout. I have not measured how often the overlap happens.
- The queue also has a dead-letter redrive after 5 receives.

### Timeouts and data-sync jobs

- A long extraction cannot assume it finishes inside one invocation.
- Design it to check its remaining time, stop cleanly with a saved cursor, and resume later.
- DevRev's AirSync docs describe a soft timeout capped at ten minutes, with a hard kill at 1.3 times that.
- My FieldSync extractor is budget-checked and resumable. I never ran it inside a real Lambda deadline.
- The module has a small sketch that checks the context deadline against a safety margin. It compiled and its test passed in a scratch module. It is not from my repo.
- If one page takes longer than the safety margin, the margin is wrong and the hard kill wins.
- So treat the margin as a tunable measured against the slowest page.
- Save state only after a page is fully applied. A kill between pages loses no work and replays at most one page.
- The write side must be idempotent (safe to repeat) for that replay. That is what my version-gated upserts are for.
- I have not measured page times against a real customer API.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Lambda | AWS runs my function once per event; I manage no server. |
| Cold start | Extra time to create a fresh environment for the function. |
| Warm | Reusing an environment that already exists. |
| Reserved concurrency | A cap on how many copies of a function run at once. |
| Visibility timeout | How long an SQS message stays hidden while being processed. |
| RDS Proxy | A connection pool service in front of the database. |
| `provided.al2023` | The custom Lambda runtime where my Go binary is named `bootstrap`. |

**Say it in one breath:** Lambda runs my handler per event, so I build costly things once, cap concurrency, and make long jobs resumable.

---

## Phase 2: Adapting an HTTP service to Lambda

**Analogy: a plug adapter for foreign sockets.** The appliance (my router) is the same. The adapter lets it fit the wall (API Gateway) abroad.

### How an ordinary router runs in Lambda

- An adapter library converts the API Gateway event into a normal `http.Request`.
- It calls my router. Then it converts the response back.
- I use `aws-lambda-go-api-proxy` with its `httpadapter`, for the HTTP API payload format version 2.0.
- The router is the same code that `cmd/server` mounts under `net/http`. One handler, two runtimes.
- So local development behaves like the deployed shape, at least at the HTTP layer.

### Why not one Lambda per route

- One function behind one router is simpler to build, test and keep consistent.
- The costs: a bigger deployment unit, shared permissions, and a cold start that includes the whole router.
- I made that trade to keep local and deployed code identical.
- I would revisit it if one route needed very different memory or scaling.

### The webhook receiver Lambda and how I made it testable

- `main` loads config, opens a pgx pool, and calls `lambda.Start` with the adapter's `ProxyWithContext`.
- A small `newAdapter(cfg, inbox)` function builds the adapter.
- The test can then create it with an in-memory inbox. No database and no secret.
- I put setup in `main`, not `init`. `init` also runs under `go test` and would die without `WEBHOOK_SECRET` and a database.
- Flow: request -> adapter -> router -> HMAC verification -> insert into inbox -> 202.
- The seam is `newAdapter` taking the config and an `Inbox` interface, so the test replaces the database.
- By contrast, `cmd/lambda` uses `init()` and is harder to test.

### What the Lambda entrypoint leaves out

- It leaves out anything needing permissions or a transport a Lambda does not have.
- In `cmd/lambda` I skip `EnsureBucket`. Terraform owns the bucket. A cold-start `CreateBucket` call would be extra IAM surface.
- The `/ws` route is built only so the router signature matches.
- It is unreachable, because an HTTP API does not carry WebSockets.
- A separate WebSocket API and notifier Lambda own that in the design.
- Honest caveat: the WebSocket path exists only as design and Terraform. I never ran it.

### Testing the adapter without AWS

- I build real `events.APIGatewayV2HTTPRequest` values in the test.
- I sign them with the same HMAC scheme as the vendor, and call `ProxyWithContext` directly.
- The table covers four cases:
  - A valid signature gives 202 and one stored row.
  - A base64-encoded body still verifies against the raw bytes.
  - A wrong secret gives 401 and nothing stored.
  - Another system's path gives 404.
- I ran these tests and they pass.
- The boundary: the event shape comes from the documented payload format. I never saw real API Gateway header and body encoding.
- So a surprise such as a differently cased header is still possible in a real account.
- The base64 case matters because the signature is over exact bytes. Decoding wrongly would silently turn valid deliveries into 401s.

### Could my streaming agent console run behind this adapter?

- Not as written.
- The console streams server-sent events with a request timeout that defaults to 120 seconds.
- I recall that an API Gateway HTTP API caps integration time at about 30 seconds, and the proxy adapter returns a buffered response. Verify both in the current AWS docs.
- I know Lambda has a response-streaming option. I have not used it. I would not claim it.
- For a connector-style workload the realistic shape is a short webhook receiver, with long work done by a queue consumer.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| API Gateway | The AWS front door that turns HTTP requests into Lambda events. |
| Adapter | Code that converts between two interfaces. |
| HTTP API payload v2.0 | The event format API Gateway sends to Lambda. |
| `init()` | Go code that runs once when the process starts. |
| Seam | A place where a test can swap a real part for a fake. |
| Server-sent events (SSE) | A one-way stream from server to browser over HTTP. |

**Say it in one breath:** An adapter runs my normal router in Lambda, and an interface seam lets me test it without AWS.

---

## Phase 3: Terraform modules, state, and validating without applying

**Analogy: an architect's blueprint, checked for typos but not yet built.** Validate checks that the drawing is well-formed. It does not prove the council will approve it or that the building stands.

### Modules and state

- A module is a folder of Terraform that I call with inputs and read outputs from. I reuse infrastructure like I reuse a function.
- State is the file where Terraform records which real resources it created, so the next run can work out what to change.
- My FieldSync stack has modules for network, secrets, database, auth, storage, compute, api, websocket, eventing and webhook. They are wired together in one `envs/local` root.
- I did not set up a remote state backend. Nothing was applied to a real account.

### validate, plan and apply

- `validate` checks that the configuration is syntactically and type-correct. It contacts no cloud.
- `plan` computes what would change against real or emulated state.
- `apply` makes the change.
- I ran `init` and `validate`. I never ran `plan` or `apply` against a real AWS account.

### Making validate work with no AWS account

- The root has a provider block with placeholder credentials and `skip_*` flags, so the provider never calls AWS.
- CI and my Makefile run `init -backend=false` and `validate`.
- Catch: `filebase64sha256` on the Lambda zip needs the file on disk. So the Makefile builds the real zips first.
- The provider-block comment says `plan` also works without credentials. I have not tested that. Treat it as unproven.
- The block is a validate-only trick. It is not a way to deploy.
- The point: the HCL is type-checked on every PR with no secrets in CI.

### How a module is wired into the root

- The root passes outputs of one module into inputs of the next. Dependency order follows from references.
- The webhook module gets the API id and execution ARN from the `api` module, and the secret from `secrets`.
- `system` is one variable. It sets both the route path and the `EXTERNAL_SYSTEM` environment variable. They cannot drift apart.
- That removes a class of "route says one thing, config says another" bugs.

### What validation proves, and what to do before a first real apply

- It proves every module parses, types and references correctly. Nothing more.
- It cannot show that AWS accepts the values, that IAM allows the calls, or that the plan is what I intend.
- streampulse's ADR-0019 makes this explicit.
- `envs/local` is applied only to the moto emulator. `msk`, `vpc` and `eks` are validate-only.
- An emulator would give a green result that says nothing about isolation or permissions.
- The ADR records a real oddity: a second `plan` against moto is not empty. 3 resources show in-place changes.
- The ADR blames moto not returning tags and re-serialising JSON.
- Before a first real apply I would:
  - Add a remote backend with locking and encryption, since state can hold secret values.
  - Run `plan` in CI with a read-only role, and review it.
  - Apply a saved plan from a protected branch.
  - Start in a throwaway account.
- I have done none of that. It is a plan, not history.
- streampulse also has a validate-only root that says it must never be planned or applied.

### Has my CI Terraform job passed?

- I do not know. I found a likely failure.
- The `fieldsync-ci` job makes one placeholder zip under `modules/compute/build`.
- But the eventing, websocket and webhook modules also call `filebase64sha256` on their own zips.
- I reproduced a clean-checkout copy locally with only that one placeholder. `terraform validate` returned errors from those three modules. So the job would be red as written.
- The `ticketing-ci` job avoids this by running `make build-lambda` first.
- I validated locally with Terraform 1.14.2. CI pins 1.9.0, which I have not run.
- There is no record in the repo of either workflow running on GitHub's runners. Check the Actions tab first.

### One command for every module, and the lock file

- streampulse's `make tf-validate` runs `terraform fmt -recursive -check`.
- Then it loops `init -backend=false` plus `validate` over every module and both roots.
- It uses a local provider cache, so it works offline after the first init.
- I commit the lock file only for the two roots. It pins the exact provider build and hashes.
- State and `.terraform` are git-ignored, because state can contain secrets.
- It is a local check. It is not a CI job in that repo.

### Follow-up: guardrails for log retention and an error alarm

- Make the log group explicit so retention is set. The default group never expires.
- Add an alarm on the Lambda `Errors` metric.
- The module's snippet is not from my repo. I ran `validate` and `fmt -check` on it in a scratch directory with the AWS provider 6.x and placeholder credentials.
- That proves syntax and references only. A real apply would still need an SNS action and a real account.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Terraform | A tool that creates cloud resources from code (IaC, infrastructure as code). |
| Module | A reusable folder of Terraform. |
| State | Terraform's record of what it created. |
| `validate` / `plan` / `apply` | Check syntax / preview changes / make changes. |
| Backend | Where state is stored (local file or remote). |
| Lock file | Pins exact provider versions. |
| Emulator (moto) | A fake AWS for local testing. |

**Say it in one breath:** I validate Terraform with placeholder credentials, and I know that proves syntax only, not that AWS accepts it.

---

## Phase 4: Secrets and least-privilege IAM

**Analogy: a hotel key card.** Each guest gets a card that opens only their room, not the whole building. And you do not write the door code on the wall.

### Least privilege and execution roles

- Least privilege: each identity gets only the actions it needs, on only the resources it touches.
- A Lambda gets permissions from its execution role, which it assumes automatically. So I never put long-lived AWS keys in the code.
- In my webhook module the role has only the AWS-managed VPC access policy. The receiver calls no AWS API.
- That is the smallest grant I could justify from reading the code.

### Why not put the secret in code or config

- Code and config files end up in git, in logs and on laptops.
- Rotating a secret would need a redeploy.
- I generate secrets with Terraform's `random_password` and store them in Secrets Manager.
- Honest point: the value still reaches the function as an environment variable. That weakness comes below.

### Deriving a policy from the code

- I list the SDK calls a service actually makes. I grant only those actions on only those resources.
- In streampulse the archive compactor does list, get, put and delete on S3 objects.
- Its policy has exactly those actions: `s3:ListBucket` on the bucket, and object actions scoped to `tenant=*` keys.
- The file marks each policy as verified-from-code or unverified. Unverified ones say so in their description.
- The mapping from SDK call to IAM action is from the AWS docs as I remembered it. The file tells me to verify it.
- A policy that looks right is not evidence it is right.
- The policies are defined but not evaluated, because the emulator does not enforce IAM.

### The webhook role and secret

- The role trusts only the Lambda service and carries the managed policy for logs and network interfaces.
- The secret is generated by `random_password` and stored in a Secrets Manager secret.
- An operator copies it into the vendor's webhook settings.
- The invoke permission for API Gateway is scoped to the single route path, not a wildcard.
- My phrasing: "this is the smallest grant I could justify, and here is the weakness".

### The environment-variable weakness

- I defend it as a conscious simplification, and I name the weakness first.
- The design doc: anyone with `lambda:GetFunctionConfiguration` can read environment variables.
- The stronger option is a `GetSecretValue` call at cold start with one IAM grant. I did not build it, to keep one pattern. The database password uses the same pattern.
- Three more gaps I found when I re-read my code:
  - `DATABASE_URL` is built with the password inside. So the password is in the environment, and in Terraform state too.
  - The secrets module comment says the password is never in state. But a `random_password` result is stored in state. Verify against the provider docs before repeating either claim.
  - The compute role grants `secretsmanager:GetSecretValue`, yet my Go code makes no Secrets Manager call. That is unused permission, the opposite of least privilege.
- None of this was tested against a real account.
- Rotation is not implemented. The receiver has one secret and no dual-verify window.

### Proving least privilege

- I would not trust my reading of the code. I would test it in a real account.
- Usual tools: the IAM policy simulator, Access Analyzer, and a policy generated from CloudTrail activity.
- I have not used any of them on this stack. Verify their current behaviour in the AWS docs.
- ADR-0019 records that an emulator does not enforce IAM. So an apply against moto cannot show a denied call.
- In `ticket-booking` the seven functions share one execution role.
- The Terraform comment says one role per function would be stricter and is future work.

### Secrets for a customer-facing connector

- I would never read a customer credential from an environment variable in a shared function.
- I would fetch it at runtime from a secret store, scoped per tenant.
- I would cache it in memory briefly, log only a secret's name and never its value, and support rotation with two valid values during a window.
- My agent console and webhook receiver do not do per-tenant secrets. This is design reasoning, not something I built.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| IAM | AWS's system for who may do what. |
| Execution role | The identity a Lambda assumes to get permissions. |
| Least privilege | Grant only the actions and resources actually needed. |
| Secrets Manager | An AWS store for secrets. |
| `random_password` | A Terraform resource that generates a password. |
| ARN | The unique name of an AWS resource. |
| Access Analyzer | An AWS tool that checks policies for broad access. |

**Say it in one breath:** I give each function the smallest grant I can justify, and I admit my webhook secret still sits in an environment variable.

---

## Phase 5: CI/CD (eval gates, test pipelines, what runs where)

**Analogy: a factory quality line.** Every item passes through checks before it leaves. A cheap check always runs and always stops bad items. An expensive check needs a human to read the result.

### What CI does on a pull request

- For FieldSync: build the Go code, run `go vet` and `go test`, build the web app, run `terraform validate`.
- The workflow is limited to `offline-sync-app/**`, so unrelated monorepo changes do not trigger it.
- It has no deploy step, on purpose. Real AWS access was never approved.
- I have not seen these jobs run on GitHub's runners. I describe what the files do, not a run history.
- CI cross-compiles for linux/arm64 because the Lambda target is `provided.al2023` on arm64. A laptop build does not prove the Lambda binary builds.
- The step writes to `/dev/null`, so it is a pure compile check. It catches a platform-specific import before a failed deploy.

### The Go job, step by step

- Check out the code.
- Take the Go version from `go.mod`, so CI cannot drift from the module.
- Run build, vet and test.
- Then the arm64 cross-compile.
- Each step fails for a real reason. That matters more to me than many steps.
- Weak spots: no lint step, no race detector run, no coverage reporting.
- Say what each step guards against. Volunteer the missing steps before they ask.

### The two eval gates

- `agent-eval` is deterministic. It runs pytest and a golden trajectory suite with a scripted fake model and no network. So it can gate a pull request reliably.
- `eval-gate` has two tiers.
- Tier 1: a free parity check that fails if the eval prompt drifts from the prompt the server ships.
- Tier 2: a model tier that installs Ollama on the runner, pulls two small models and runs promptfoo.
- The workflow comment says the model tier can be red for an expected reason. So I read the output, not the badge.
- Honest status: `agent-eval` was run step by step on Python 3.12 in Docker, not on GitHub's runners.
- `eval-gate` passes locally. My study guide records it as not yet run on a real runner. Verify before citing.
- Lead with the two-tier idea: a cheap deterministic gate that always blocks, and an expensive model gate whose red result needs a human read.
- Do not say either has gated a real merge.

### Where an eval gate helps and hurts

- It helps when it is cheap, deterministic and tied to the exact artifact that ships.
- My parity check derives the rules from the server's real prompt and fails if the eval prompt lacks one.
- It exists because on 2026-09-07 the "must decline" case failed in the harness while the server answered correctly. The cause was two different prompts.
- A model-based gate hurts when it is slow, flaky or unpinned.
- Mine installs Ollama with `curl | sh` and runs `npx promptfoo@latest`. A new release could change results with no change in my repo.
- A failed assertion makes promptfoo exit with code 100. I verified that locally. So a red case fails the job.
- That is a fact about the tool, not about model quality.
- I have never seen this gate block a merge in anger. I would not claim it as an operating practice.

### How I would pin and speed up the model tier

- Pin the promptfoo version and the Ollama install.
- Cache the model files between runs.
- Run the model tier on a schedule or a label, not every pull request.
- Keep the deterministic tier as the required check.
- I have not done this. Present it as the next change.
- Caution on path filters: if a required check never runs because changed files do not match its paths, the pull request can wait on it. Verify in GitHub's current docs.

### Designing the deploy half I left out

- Keep pull request jobs read-only.
- Add a separate deploy workflow on the main branch that authenticates to AWS with OIDC (short-lived tokens, so no stored long-lived keys).
- It runs `terraform plan`, saves the plan, and applies that saved plan behind a protected environment that needs approval.
- The trade-off: slower deploys for a reviewable, reproducible change.
- The module's workflow is illustrative. I checked it parses as YAML. I never ran it against a real account. The role ARN is a placeholder.
- Why apply a saved plan: what was reviewed is exactly what runs. Nothing drifts between review and apply.
- Plan and apply can sit in one job. Split them across an approval gate only if a human must approve in between.
- In a real setup I would also run the plan step on pull requests with a read-only role.
- My repos have no `envs/prod` and no remote state. This is design, not code I wrote.

### What the Java project's CI adds

- streampulse CI has a concurrency group that cancels an in-progress run when new commits land on the same ref.
- It has a 20 minute job timeout and a formatting check.
- Test and coverage artifacts upload with `if: always()`, so I get reports exactly when tests fail.
- The file states its own rule: a pipeline nobody trusts is worse than none. Every step must fail for a real reason.
- It has no Terraform step. The header says Terraform validate would arrive later. So it stays a local `make tf-validate`.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| CI/CD | Automatic build and test (CI), and automatic release (CD). |
| Gate | A check that must pass before a change can merge. |
| Golden trajectory suite | Saved expected agent runs used as tests. |
| Parity check | Confirms two copies of something (the prompt) still match. |
| promptfoo | A tool that runs evals on prompts and models. |
| OIDC | Short-lived identity tokens instead of stored keys. |
| Protected environment | A deploy target that needs approval to run. |

**Say it in one breath:** My CI builds, tests and validates with no deploy; a cheap eval gate blocks, and a model gate needs a human read.

---

## Phase 6: Observability (structured logs, metrics, traces, health checks, error surfacing to a customer)

**Analogy: a hospital.** Metrics are the heart monitor beeping. Logs are the patient's notes. Traces follow one patient through every department. A health check asks "can you take a patient right now?".

### Logs, metrics and traces

- Logs are timestamped records of events.
- Metrics are numbers aggregated over time, such as error rate and latency.
- Traces follow one request across services.
- I use metrics to notice a problem, logs to find what happened in one request, and traces to see where time went.
- The Go agent console writes structured JSON logs.
- streampulse exposes Prometheus metrics through Micrometer.
- I wrote an OpenTelemetry collector config for traces.
- No service ever sent a trace. More below.

### Health checks

- A health check is an endpoint that tells a platform whether to send traffic to an instance.
- Liveness says the process is up.
- Readiness says it can do its job, including reaching its dependencies.
- My `/healthz` reports dependency health on purpose. A server that is up but cannot reach its model should not say "ok" and hide the outage.
- The handler builds a status with the provider, model and whether retrieval is enabled.
- For the Ollama provider only, it probes the model server with a two second timeout.
- If the probe fails, status becomes `degraded` with the error, and the HTTP code is 503. A load balancer or monitor can see it.
- Limit: one endpoint serves both liveness and readiness. For other providers there is no probe at all.
- I would split it before putting it behind an orchestrator.
- Lead with: dependency health is not process liveness.

### Logs that let someone debug one request

- The logger is the standard library `slog` with the JSON handler.
- The chat handler derives a child logger carrying fields such as question length and turn count.
- It adds retrieval count and retrieval latency as it learns them.
- On completion it logs prompt tokens, completion tokens and latency in milliseconds.
- On failure it separates a client that hung up (only logged) from a real generation failure (logged as an error and reported in the stream).
- My phrase: "one child logger per request, fields added as they become known".
- The gap: no request or correlation id in these lines. I have not shipped them to any log backend.

### What the customer sees when it fails

- Today it is not good enough.
- When retrieval fails, the handler refuses to degrade into an ungrounded answer. That is the correct decision.
- But it sends an error frame with "retrieval unavailable:" followed by the raw error string.
- The generation-failure path also sends `err.Error()` to the client.
- That helps me. It is wrong for a customer. It can leak internal hostnames or driver messages. It gives the customer nothing to quote to support.
- What I want: a stable, safe message and a correlation id in both the response and the log line. A ticket id then leads to exactly one log entry.
- The module's snippet is illustrative. I compiled it and its test passes in a scratch module. The test asserts the response hides the cause and that the id links to the log.
- I have not wired it into the agent console.

### Surfacing failures for a sync connector

- Surface per-item failures, not just one big error. A sync that fails one record in ten thousand should say which record and why.
- My FieldSync design counts a message that keeps failing, moves it to a dead-letter table with the raw payload, reason and attempts, and keeps the queue moving.
- Not built: alerting on dead-letter growth, and replay tooling. The doc says so.
- The log lines in that path carry the delivery id.
- But the SQS consumers use plain `log.Printf` lines, not structured fields. I would change that first.

### Alerting on an SLO without paging on every blip

- An SLO is a service level objective, a target such as "99.9 percent of requests succeed".
- I use multiwindow, multi-burn-rate alerts.
- A page needs both a long window and a short window above the threshold. It fires on a sustained burn and clears soon after the problem ends.
- In streampulse the fast-burn rule compares the one hour and five minute error ratios with 14.4 times the 0.1 percent budget.
- Every alert carries a runbook link.
- Honest status: the SLO numbers are targets.
- The rule tests exist. My phase notes record that `promtool` had never been run on them, and that `make up-obs` did not load the rules.
- So I describe these as drafts. Verify the current repo state before repeating it.

### Traces

- I wrote an OpenTelemetry collector config.
- It has a traces pipeline to Tempo, a logs pipeline to Loki, and a memory limiter first.
- It deliberately has no metrics pipeline, because Micrometer already feeds Prometheus.
- No service attached the Java agent. No trace has been produced. I will not say I have distributed tracing.
- Next step: attach the agent to one service, send one request, and look for the span in Tempo. I have not run that experiment.

### What I would alarm on for the Lambda stack

- In `ticket-booking` the observability module turns log lines into metrics with metric filters, and alarms on them.
- It alarms when any consumer dead-letter queue has a visible message. That means five real delivery attempts failed.
- It also has alarms for saga compensations, RDS Proxy session pinning and Redis evictions, plus a dashboard.
- The conflict-rate alarm is openly a placeholder: an absolute threshold of 1000, until a ratio expression is checked against real traffic.
- All of it is validated HCL, never applied. I cannot tell you whether the thresholds are right.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Structured log | A log line with named fields (JSON), easy to search. |
| Metric | A number measured over time. |
| Trace / span | One request's path across services / one step in it. |
| Liveness / readiness | "Process is up" / "ready to do its job". |
| Correlation id | An id shared by the response and the log line for one request. |
| SLO / burn rate | A target / how fast the error budget is being spent. |
| OpenTelemetry (OTel) | A standard way to collect traces, metrics and logs. |

**Say it in one breath:** I log structured JSON and report dependency health, but I still lack correlation ids, safe error messages and a real trace.

---

## Phase 7: Containers and local parity (Docker, compose)

**Analogy: a film set vs the real city.** The set looks right from the camera angle (the HTTP layer). But the real city has weather, permits and traffic the set never reproduces.

### Why Docker Compose

- Compose starts the real dependencies with one command, such as Postgres. I do not install them on my laptop. Every run starts from the same versions.
- In FieldSync it starts Postgres 16, a Cognito emulator, MinIO for S3 and a moto server. `make compose-up` wraps it.
- streampulse uses profiles, so nothing starts unless I ask. The whole estate would use about 8 to 10 GB of RAM by its own comment.
- I use compose for dependencies. I run my own code on the host.
- A compose health check tells compose and tests when a dependency is ready, not merely started.
- My Postgres service runs `pg_isready` every 5 seconds with 10 retries.
- Without it, a test can start before the database accepts connections and fail for a reason unrelated to my code.

### Local AWS substitutes, and a choice I had to change

- I tried LocalStack first and replaced it. Its image refused to start without an auth token. The compose comment says I verified that directly.
- So I used MinIO for S3 and moto for the other AWS-style APIs.
- The Go client targets a custom endpoint with path-style addressing, so the swap needed no Go changes.
- Weak point: the FieldSync compose file uses unpinned `latest` tags for MinIO and moto. That is not reproducible.
- The streampulse file pins tags, and says why. For moto, `latest` was a 5.2.3.dev build, and 5.2.2 was verified with `docker manifest inspect`.
- Pinning is the pattern I would carry back to FieldSync.
- Emulators are permissive. They are evidence about wiring, not about AWS behaviour.

### Separating an observability stack with a second compose file

- A second compose file adds services and extends two existing ones. I start both files with a profile.
- The comment points out that relative paths resolve against the first file's directory. That is an easy mistake.
- Traces and logs live in container filesystems, so `down` loses them.
- When I last read my phase notes, the Makefile target did not load this override.
- Present it as the "compose merge" pattern. Say the wiring was drafted, not run end to end.

### The container image recipe

- One Dockerfile recipe for every Spring Boot service.
- It extracts the jar into layers. A code-only rebuild re-ships a few kilobytes instead of tens to hundreds of megabytes.
- It runs as a numeric non-root user, so a kubelet can verify it.
- Application files are root-owned. The process cannot rewrite its own code.
- Heap is 75 percent of the container limit, not a fixed `-Xmx`.
- It exits on out-of-memory. The orchestrator restarts it instead of leaving it in an undefined state.
- The reasoning is in the file's own comments.
- Not verified: a built image. There is no recorded `docker build` in the milestones. The ADR it cites is not in the ADR folder. The layer-size claim is the comment's, not my measurement.
- So I present this as a reviewed recipe.

### Does local parity extend to Lambda?

- Only partly.
- At the HTTP layer the same router runs locally and in the Lambda adapter. CI cross-compiles for linux/arm64. So the code path and build target are checked.
- Compose does not run the Lambda runtime. Cold start, the execution role, VPC networking and real event payloads are not reproduced.
- Emulators do not enforce IAM.
- My Lambdas ship as zip files on `provided.al2023`, not container images. I did not use the Lambda runtime interface emulator.
- For closer parity I would add that emulator or a container-image deployment.
- I would still treat a real staging account as the only real test.

### The Spring Cloud Function compactor

- The compactor is a plain `java.util.function.Function`: a request in, a report out. No framework type in the signature.
- So it runs in-process and in tests.
- The Gradle file says plainly that it has never been deployed as a real serverless function. A Lambda adapter would be a deploy-time concern, not added.
- The design (ADR-0020): write, re-read, commit a manifest, and only then delete inputs. A crash at any point is recovered without duplicates.
- Its tests prove that against objects the tests generate. The ADR admits no service writes this archive.
- Would I pick Lambda for it? It is a reasonable fit for a periodic job per partition.
- The Lambda timeout and ephemeral disk decide it. Plan one partition per invocation and resumable runs.
- Check the maximum timeout and `/tmp` size in the current AWS docs before sizing.
- I have no measurement of how long a real partition takes. No real data was ever written to the archive.
- A JVM with Spring has a heavier cold start than my Go binaries. I have not measured it.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Docker Compose | Starts several containers together from one file. |
| Profile | A label that lets you start only some compose services. |
| Health check | A command that reports whether a container is ready. |
| Image layer | A cached slice of a container image. |
| Non-root user | Running as a limited user, not as root. |
| Pinned tag | A fixed image version, not `latest`. |
| Emulator | A fake service that imitates a cloud API locally. |

**Say it in one breath:** Compose gives real local dependencies, emulators prove wiring not AWS behaviour, and only a staging account is the real test.

---

## Mix-ups to avoid

- Do not say "validated" means "deployed". Terraform was only validated. Nothing was applied to real AWS.
- Do not mix up liveness (process is up) with readiness (dependencies are reachable).
- Do not say the webhook secret is protected beyond Secrets Manager storage. It is an environment variable.
- Do not say CI is green. There is no run history, and the `fieldsync-ci` Terraform job would fail on a clean checkout in my local reproduction.
- Do not say an emulator proves permissions. Emulators do not enforce IAM.
- Do not say 50 reserved concurrency was measured. It is a design value.

## What I built vs what I only know

**Built [L], never on a real AWS account:**

- Go Lambdas behind an HTTP adapter, with a testable webhook receiver and synthetic API Gateway event tests (these tests ran and pass).
- Terraform modules, validated with placeholder credentials (Terraform 1.14.2). streampulse `envs/local` was applied only to the moto emulator.
- CI workflows as files: Go build/vet/test, arm64 cross-compile, Terraform validate, deterministic and model eval gates.
- A dependency-aware `/healthz`, structured `slog` logs, a draft SLO alert rule, an OTel collector config, and a hardened Dockerfile recipe.

**Shipped [P]:** nothing in this module.

**Knowledge only [K] (verify before an interview):**

- AWS limits and guidance: 15 minute maximum timeout, memory range, concurrency quota, API Gateway timeout, SQS visibility multiple, Lambda response streaming.
- IAM policy simulator, Access Analyzer, and CloudTrail-generated policies. I have not used them on this stack.
- The OIDC deploy workflow and the saved-plan flow. Design only.

**Not built or not claimed:**

- No deploy, no remote state, no `envs/prod`.
- No measured cold start, latency or throughput.
- No distributed tracing, no tested or loaded alert rules (`promtool` not run, `make up-obs` did not load the rules).
- No proof of least privilege. One policy grants an action the code never calls.
- No built container image on record. The Spring compactor never ran as a Lambda.
- No claim that `eval-gate.yml` or `agent-eval.yml` has run on a real GitHub runner.
- The inbox worker is not deployed. A receiver Lambda would fill `webhook_inbox` and nothing would drain it.
