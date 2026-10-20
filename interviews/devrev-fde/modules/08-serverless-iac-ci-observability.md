# Module 08 — Serverless, IaC, CI/CD & observability

> This module covers the part of the DevRev FDE job description that says "hands-on deployment experience on serverless or edge platforms, plus CI/CD, containers, and observability practices" and "logging, error surfacing, and telemetry". The code lives in three of my own builds: `GolangExercise/offline-sync-app` (FieldSync, Go Lambdas plus Terraform), `GolangExercise/ticket-booking` (more Lambdas, a Terraform observability module), and `streampulse` (Terraform against emulators, a Spring Cloud Function, a Prometheus/OTel stack, a Dockerfile). The agent-eval workflows and the `/healthz` handler live in `AI`. Everything here is lane [L], my own work. Nothing was ever applied to a real AWS account: Terraform was only validated (Terraform 1.14.2 locally), and streampulse's `envs/local` was applied only against the moto emulator.

## Phases at a glance

| Phase | Purpose | Main code |
|---|---|---|
| 1. Serverless fundamentals | Handler model, cold start, time and memory limits, concurrency, and why they shape the code | `ticket-booking/cmd/server-lambda`, `ticket-booking/infra/terraform/modules/compute` |
| 2. Adapting an HTTP service to Lambda | Run the same router locally and behind API Gateway, and test the adapter without AWS | `offline-sync-app/cmd/webhook-receiver-lambda`, `cmd/lambda` |
| 3. Terraform modules, state, validate without apply | Prove the HCL is well-formed with no account, and know what that does not prove | `offline-sync-app/infra/terraform/envs/local`, `streampulse/infra/terraform/envs/validate` |
| 4. Secrets and least-privilege IAM | One role per function, grants derived from code, honest about env-var secrets | `offline-sync-app/infra/terraform/modules/{secrets,webhook,compute}`, `streampulse/.../modules/iam` |
| 5. CI/CD | What runs on every PR, what gates, what deliberately does not deploy | `GolangExercise/.github/workflows`, `AI/.github/workflows`, `streampulse/.github/workflows/ci.yml` |
| 6. Observability | Structured logs, metrics, traces, dependency health, and what the customer sees on failure | `AI/fe-hands-on/server/stream.go`, `streampulse/docker/observability`, `ticket-booking/.../modules/observability` |
| 7. Containers and local parity | Compose for local dependencies, a hardened image recipe, and where local differs from Lambda | `offline-sync-app/docker-compose.yml`, `streampulse/docker`, `streampulse/deploy/docker/Dockerfile` |

## Phase 1 — Serverless fundamentals (handler model, cold starts, time and memory limits, concurrency)

### 🟢 Beginner

**Q:** What is a Lambda function, and how is it different from a server I run myself?

**A:** A Lambda function is a handler that AWS invokes once per event, and AWS decides how many copies of my code are running at any moment. I do not manage a machine or a listening port, so the unit I write is "one event in, one result out". My Lambdas are Go binaries built for `provided.al2023` on arm64, where the binary has to be named `bootstrap`. The trade I make is that I give up long-lived process state in exchange for no server management and scaling per request. Since none of mine was ever deployed to a real account, I describe this from the design and the Terraform, not from production traffic.

**Q:** What is a cold start?

**A:** A cold start is the extra time when AWS has to create a fresh execution environment for my function before it can run the handler. In that start-up phase my package-level code, `init()` and `main()` run until they call `lambda.Start`. After that the same environment can serve many invocations, which are called warm. I have not measured a single cold start, because nothing ran on AWS, so I would never quote a number for my functions.

### 🟡 Intermediate

**Q:** Where do you put expensive setup like the database pool, and why?

**A:** I put it in start-up code, outside the per-request handler, so a warm environment reuses it. In `server-lambda` the pool is built once in `init()`, and the handler only calls the adapter. There is a deliberate comment that I do not `defer Close()` there, because a warm environment is reused and closing a pool after the first request would defeat pooling. The failure mode is that `log.Fatalf` in `init()` kills the environment at start-up, so a bad config shows up as a failed cold start on every new environment rather than as a clean 500.

**Source:** `GolangExercise/ticket-booking/cmd/server-lambda/main.go:23-45`
```go
var adapter *httpadapter.HandlerAdapterV2

func init() {
	cfg := config.Load()
	app, err := wiring.New(context.Background(), cfg)
	if err != nil {
		log.Fatalf("wiring: %v", err)
	}
	// Deliberately no defer Close(): a Lambda execution environment is
	// reused across warm invocations, and app.Pool is a connection POOL —
	// closing it after the first request would defeat the entire point of
	// pooling in a serverless context (docs/plan.md's own reasoning for
	// RDS Proxy existing at all).
	adapter = httpadapter.NewV2(app.Router)
}

func handler(ctx context.Context, req events.APIGatewayV2HTTPRequest) (events.APIGatewayV2HTTPResponse, error) {
	return adapter.ProxyWithContext(ctx, req)
}

func main() {
	lambda.Start(handler)
}
```

**How to talk about it:** Point at the two phases. Everything in `init()` is paid once per environment, and `handler` is the only code paid per request. Then offer the contrast in the next question, because not every one of my Lambdas keeps its pool.

**Q:** Your scheduled Lambdas open and close a pool inside the handler. Is that inconsistent?

**A:** It is intentional, and I can defend it, though I have not measured the cost. `saga-worker-lambda` is a scheduled catch-up job that runs rarely and for a short time, so a pool that lives for one invocation is simple and leaks nothing. The API Lambda serves bursts of requests, so a warm pool matters there. The cost of the per-invocation pool is one fresh connection setup per run, which I expect is small next to the work but did not time.

**Source:** `GolangExercise/ticket-booking/cmd/saga-worker-lambda/main.go:24-36`
```go
func handler(ctx context.Context) error {
	cfg := config.Load()

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()
	q := db.New(pool)

	lock := holdlock.New(cfg.RedisAddr)
	defer lock.Close()
	inv := inventory.New(pool, q, lock, time.Duration(cfg.HoldTTLSeconds)*time.Second, cfg.MaxSeatsPerHold)
```

**How to talk about it:** Say "one-shot job, one-shot pool" and move on. If they push, the honest answer is that I chose by reasoning, not by measurement.

### 🔴 Senior

**Q:** How do memory, timeout and concurrency interact in your design, and what breaks first under load?

**A:** Memory, timeout and reserved concurrency are one decision, because Lambda gives CPU in proportion to memory and every concurrent execution holds its own database connections. In `ticket-booking` the API function has 512 MB, a 15 second timeout and a reserved concurrency of 50, and the Terraform comment says the cap exists to bound how many pgx connections that function can open against RDS Proxy. The trade-off is that reserved concurrency protects the database, and it also turns a traffic spike into throttled requests instead of a slow database, which is the right failure for a seat-booking write path, but I would argue for each function separately. What breaks first is the database connection budget, not the function, and a stuck handler is capped by the timeout. The number 50 is a design choice, not something I measured on Lambda, because I never load-tested on AWS, so the only claim is that the cap is wired and validated in HCL. The 15 minute maximum timeout, the memory range and the default regional concurrency quota are AWS facts that you should verify in the current AWS docs before quoting.

**Source:** `GolangExercise/ticket-booking/infra/terraform/modules/compute/main.tf:13-24`
```hcl
  functions = {
    server = {
      handler         = "server-lambda"
      memory_mb       = 512
      timeout_seconds = 15
      # The write path (docs/plan.md "compute": "reserved_concurrent_executions
      # on the write path") -- caps how many concurrent executions can ever
      # run, which caps how many concurrent pgx connections this function
      # alone can open against RDS Proxy, regardless of how hard API Gateway
      # is hit.
      reserved_concurrent_executions = 50
    }
```

**Follow-up they will ask:** "Why is a 30 second SQS visibility timeout with a 30 second function timeout a problem?"

**A:** Because a message can become visible again while the first attempt is still running, which causes a duplicate delivery and extra load. In my eventing module both are 30 seconds, and I recall AWS guidance that the queue visibility timeout should be several times the function timeout, but you may want to verify the exact multiple in the current AWS docs. My consumers are protected from the damage because `sqsconsume` checks a `processed_events` table before calling the handler, so a duplicate becomes a no-op. I would still raise the visibility timeout, and I have not measured how often the overlap would happen.

**Source:** `GolangExercise/offline-sync-app/infra/terraform/modules/eventing/main.tf:36-44`
```hcl
resource "aws_sqs_queue" "queue" {
  for_each                   = local.consumers
  name                       = "${var.name_prefix}-${each.key}-queue"
  visibility_timeout_seconds = 30
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })
}
```

**Q:** Where would a Lambda timeout hurt a data-sync job like the ones DevRev connectors run, and how do you design for it?

**A:** A long extraction cannot assume it finishes inside one invocation, so I design it to check its remaining time, stop cleanly with a saved cursor, and resume later. DevRev's AirSync docs describe a soft timeout capped at ten minutes with a hard kill at 1.3 times that, so the same idea applies there. My FieldSync extractor is budget-checked and resumable, but I never ran it inside a real Lambda deadline. The sketch below shows the shape with the Lambda context deadline; it compiles and its test passes in a scratch module, but it is not from my repo.

**Illustrative (not from the repo):**

```go
const safetyMargin = 2 * time.Second

func drain(ctx context.Context, next func(context.Context) (more bool, err error)) (done int, err error) {
	for {
		if dl, ok := ctx.Deadline(); ok && time.Until(dl) < safetyMargin {
			return done, nil
		}
		more, err := next(ctx)
		if err != nil {
			return done, err
		}
		done++
		if !more {
			return done, nil
		}
	}
}
```

**Follow-up they will ask:** "What if one page takes longer than your safety margin?"

**A:** Then the margin is wrong and the hard kill wins, which is why I treat the margin as a tunable that needs measuring against the slowest page, not a constant I trust. The state I save must be written after a page is fully applied, so a kill between pages loses no work and replays at most one page. The write side has to be idempotent for that replay to be safe, which is what my version-gated upserts are for. I have not measured page times against a real customer API.

## Phase 2 — Adapting an HTTP service to Lambda

### 🟢 Beginner

**Q:** How can an ordinary HTTP router run inside Lambda?

**A:** An adapter library converts the API Gateway event into a normal `http.Request`, calls my router, and converts the response back. I use `aws-lambda-go-api-proxy` with its `httpadapter` for the HTTP API payload format version 2.0. The router itself is the same code that `cmd/server` mounts under `net/http`, so there is one handler and two runtimes. That is why local development behaves like the deployed shape, at least at the HTTP layer.

**Q:** Why not rewrite each route as its own Lambda?

**A:** For my apps one function behind one router is simpler to build, test and keep consistent. The cost is a bigger deployment unit, shared permissions, and a cold start that includes the whole router. I made that trade because it keeps the local and deployed code identical, and I would revisit it if one route needed very different memory or scaling.

### 🟡 Intermediate

**Q:** Walk me through your webhook receiver Lambda and how you made it testable.

**A:** The `main` function loads config, opens a pgx pool, and calls `lambda.Start` with the adapter's `ProxyWithContext`. The adapter itself is built by a small `newAdapter(cfg, inbox)` function, so the test can create it with an in-memory inbox, no database and no secret. I put setup in `main` instead of `init` for exactly that reason, because `init` also runs under `go test` and would die without `WEBHOOK_SECRET` and a database. The flow is request, adapter, router, HMAC verification, then an insert into the inbox that returns 202 once the delivery is stored.

**Source:** `GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda/main.go:20-37`
```go
func newAdapter(cfg twoway.Config, inbox webhook.Inbox) *httpadapter.HandlerAdapterV2 {
	verifier := webhook.NewVerifier(cfg.WebhookSecret, cfg.WebhookTolerance, time.Now)
	return httpadapter.NewV2(webhook.NewRouter(cfg.System, verifier, inbox, cfg.MaxBodyBytes))
}

func main() {
	cfg, err := twoway.LoadConfig()
	if err != nil {
		log.Fatalf("webhook-receiver-lambda: %v", err)
	}

	pool, err := pgxpool.New(context.Background(), config.Load().DatabaseURL)
	if err != nil {
		log.Fatalf("connect to database: %v", err)
	}

	lambda.Start(newAdapter(cfg, webhook.NewDBInbox(db.New(pool))).ProxyWithContext)
}
```

**How to talk about it:** Name the seam: `newAdapter` takes the config and an `Inbox` interface, so the test replaces the database. Then mention the contrast with `cmd/lambda`, which uses `init()` and is therefore harder to test.

**Q:** What does the Lambda entrypoint deliberately leave out compared with the local server?

**A:** It leaves out anything that needs permissions or a transport a Lambda does not have. In `cmd/lambda` I skip `EnsureBucket` because Terraform owns the bucket, and a cold-start `CreateBucket` call would be extra IAM surface. The `/ws` route is constructed only so the router signature matches, and it is unreachable because an HTTP API does not carry WebSockets, so a separate WebSocket API and notifier Lambda own that in the design.

**Source:** `GolangExercise/offline-sync-app/cmd/lambda/main.go:36-52`
```go
	store, err := storage.New(ctx, cfg.S3Endpoint, cfg.AWSRegion, cfg.S3Bucket, cfg.S3AccessKey, cfg.S3SecretKey)
	if err != nil {
		log.Fatalf("init S3 client: %v", err)
	}
	// No store.EnsureBucket here, unlike cmd/server: Terraform provisions the
	// real bucket (infra/terraform/modules/storage) — a cold-start CreateBucket
	// call would be redundant IAM surface a Lambda has no business holding.

	verifier := auth.NewVerifier(cfg.CognitoIssuer, cfg.CognitoAudience)
	// The /ws route this hub backs is unreachable in real deployment — HTTP
	// API (this Lambda's actual integration) doesn't do WebSocket at all; a
	// genuinely separate API Gateway WebSocket API + notifier Lambda would
	// own that in a real distributed deployment. Constructed anyway purely
	// so this Lambda can share httpapi.NewRouter's signature with cmd/server.
	router := httpapi.NewRouter(verifier, db.New(pool), pool, store, wsstub.NewHub())
	adapter = httpadapter.NewV2(router)
}
```

**How to talk about it:** Use it to show you think about what a function should not hold. The honest caveat is that the WebSocket path exists only as design and Terraform, not as something I ran.

### 🔴 Senior

**Q:** How do you test a Lambda adapter without AWS, and what does that test not prove?

**A:** I build real `events.APIGatewayV2HTTPRequest` values in the test, sign them with the same HMAC scheme as the vendor, and call `ProxyWithContext` directly. The table covers a valid signature giving 202 and one stored row, a base64-encoded body that still verifies against the raw bytes, a wrong secret giving 401 and nothing stored, and another system's path giving 404. I ran these tests and they pass. The boundary of the claim is important: the event shape comes from the documented payload format, and the real API Gateway header and body encoding was never observed, so a surprise such as a differently cased header is still possible in a real account. The base64 case matters because the MAC is over exact bytes, and decoding wrongly would silently turn valid deliveries into 401s.

**Source:** `GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda/main_test.go:57-85`
```go
func TestAdapter_ProxyEvent(t *testing.T) {
	const body = `{"event": "issue.updated",  "issue":{"id":"MJ-1"}}`
	tests := []struct {
		name       string
		event      events.APIGatewayV2HTTPRequest
		wantStatus int
		wantStored int
	}{
		{"valid signature is 202 and stored", signedEvent(testSecret, "/webhooks/mockjira", "dlv-1", body), http.StatusAccepted, 1},
		{"base64-encoded body still verifies against the raw bytes", base64Body(signedEvent(testSecret, "/webhooks/mockjira", "dlv-1", body)), http.StatusAccepted, 1},
		{"wrong secret is 401 and nothing stored", signedEvent("not-the-secret", "/webhooks/mockjira", "dlv-1", body), http.StatusUnauthorized, 0},
		{"another system's path is 404", signedEvent(testSecret, "/webhooks/other", "dlv-1", body), http.StatusNotFound, 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			inbox := memInbox{}
			cfg := twoway.Config{System: "mockjira", WebhookSecret: testSecret, WebhookTolerance: 5 * time.Minute, MaxBodyBytes: 1 << 20}

			resp, err := newAdapter(cfg, inbox).ProxyWithContext(context.Background(), tt.event)

			if err != nil || resp.StatusCode != tt.wantStatus || len(inbox) != tt.wantStored {
				t.Errorf("got %d %s, err %v, %d stored; want %d and %d stored", resp.StatusCode, resp.Body, err, len(inbox), tt.wantStatus, tt.wantStored)
			}
			if tt.wantStored == 1 && string(inbox["mockjira/dlv-1"]) != body {
				t.Errorf("stored body = %q, want the raw bytes %q", inbox["mockjira/dlv-1"], body)
			}
		})
	}
}
```

**Follow-up they will ask:** "Could your streaming agent console run behind this adapter?"

**A:** Not as it is written, and I would say so plainly. The console streams server-sent events with a request timeout that defaults to 120 seconds, while I recall that an API Gateway HTTP API caps integration time at about 30 seconds and the proxy adapter returns a buffered response, so you may want to verify both facts in the current AWS docs. I know Lambda has a response-streaming option, but I have not used it, and I would not claim it. For a connector-style workload the realistic shape is a short webhook receiver like the one above, with long work done by a queue consumer.

## Phase 3 — Terraform modules, state, and validating without applying

### 🟢 Beginner

**Q:** What are Terraform modules and state?

**A:** A module is a folder of Terraform that I call with inputs and read outputs from, so I can reuse a piece of infrastructure the same way I reuse a function. State is the file where Terraform records which real resources it created, so the next run can work out what to change. My FieldSync stack has modules for network, secrets, database, auth, storage, compute, api, websocket, eventing and webhook, wired together in one `envs/local` root. I did not set up a remote state backend, because nothing was ever applied to a real account.

**Q:** What is the difference between `validate`, `plan` and `apply`?

**A:** `validate` checks that the configuration is syntactically and type-correct without contacting any cloud. `plan` computes what would change against real or emulated state, and `apply` makes the change. I ran `init` and `validate` on my configs, but I never ran `plan` or `apply` against a real AWS account.

### 🟡 Intermediate

**Q:** How did you make `terraform validate` work with no AWS account?

**A:** The root module has a provider block with placeholder credentials and the `skip_*` flags, so the provider never tries to call AWS. Then CI and my Makefile run `init -backend=false` and `validate`. One catch is that `filebase64sha256` on the Lambda zip needs the file on disk, so the Makefile builds the real zips first. The comment in the provider block says `plan` also works without credentials, and I have not tested that, so I would treat it as unproven.

**Source:** `GolangExercise/offline-sync-app/infra/terraform/envs/local/main.tf:15-26`
```hcl
# Placeholder provider config so `terraform init`/`validate`/`plan` succeed
# with no credentials. `terraform apply` against this env targets real AWS
# and is never run automatically — it needs explicit, separate user approval,
# and real credentials this config does not provide.
provider "aws" {
  region                      = "us-east-1"
  access_key                  = "local"
  secret_key                  = "local"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}
```

**How to talk about it:** Say the block is a validate-only trick, not a way to deploy. The point is that the HCL is type-checked on every PR with no secrets in CI.

**Q:** Show how a module is wired into the root.

**A:** The root passes outputs of one module into inputs of the next, so dependency order is implied by references. The webhook module receives the API id and execution ARN from the `api` module and the secret from `secrets`. `system` is a single variable that sets both the route path and the `EXTERNAL_SYSTEM` environment variable, so they cannot drift apart.

**Source:** `GolangExercise/offline-sync-app/infra/terraform/envs/local/main.tf:149-159`
```hcl
module "webhook" {
  source                   = "../../modules/webhook"
  name_prefix              = local.name_prefix
  private_subnet_ids       = module.network.private_subnet_ids
  lambda_security_group_id = module.network.lambda_security_group_id
  api_id                   = module.api.api_id
  api_execution_arn        = module.api.execution_arn
  system                   = "mockjira"
  webhook_secret           = module.secrets.webhook_secret
  base_environment         = local.base_environment
}
```

**How to talk about it:** Use it to explain one variable driving two places, which removes a class of "route says one thing, config says another" bugs.

### 🔴 Senior

**Q:** What does your Terraform validation prove, and what would you do before the first real apply?

**A:** It proves that every module parses, types and references correctly, and nothing more: it cannot show that AWS accepts the values, that IAM allows the calls, or that the plan is what I intend. Streampulse makes this explicit in ADR-0019, where `envs/local` is applied only to the moto emulator and `msk`, `vpc` and `eks` are validate-only, because an emulator would give a green result that says nothing about isolation or permissions. That ADR records a real observed oddity: a second `plan` against moto is not empty, with 3 resources showing in-place changes, which the ADR attributes to moto not returning tags and re-serialising JSON. Before a first real apply I would add a remote backend with locking and encryption, since state can hold secret values, run `plan` in CI with a read-only role and review it, apply a saved plan from a protected branch, and start in a throwaway account. I have done none of that, so I would describe it as a plan.

**Source:** `streampulse/infra/terraform/envs/validate/main.tf:1-12`
```hcl
# VALIDATE-ONLY. This root exists so `terraform validate` can check the vpc, msk and eks modules
# together with their real wiring. It must never be planned or applied: it has no emulator to
# point at, and an emulator would not make the result meaningful anyway (ADR-0019).

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "validate-only"
  secret_key                  = "validate-only"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = "true"
}
```

**Follow-up they will ask:** "Has your CI Terraform job actually passed?"

**A:** I do not know, and I found a likely failure when I checked. The `fieldsync-ci` job creates only one placeholder zip under `modules/compute/build`, but the eventing, websocket and webhook modules also call `filebase64sha256` on their own zips. I reproduced a clean-checkout copy of the tree locally with only that one placeholder, and `terraform validate` returned errors from those three modules, so the job would be red as written. The `ticketing-ci` job avoids the problem by running `make build-lambda` first. I validated locally with Terraform 1.14.2 while CI pins 1.9.0, which I have not run. I have no record in the repo of either workflow running on GitHub's runners, so check the Actions tab before relying on a green claim.

**Source:** `GolangExercise/.github/workflows/fieldsync-ci.yml:47-64`
```yaml
  terraform-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"
      # No AWS credentials configured — this only checks the HCL itself
      # parses/type-checks, mirroring infra/terraform/envs/local's own
      # placeholder-credentials provider block. Never `plan` or `apply`.
      - working-directory: offline-sync-app/infra/terraform/envs/local
        run: |
          # Build/lambda dependency validate needs a zip on disk to exist, even
          # though this job never invokes it — a zero-byte placeholder is enough.
          mkdir -p ../../modules/compute/build
          touch ../../modules/compute/build/bootstrap.zip
          terraform init -backend=false
          terraform validate
```

**Source:** `GolangExercise/.github/workflows/ticketing-ci.yml:53-74`
```yaml
  terraform-validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: ticket-booking/go.mod
      # Cross-compiles every cmd/*-lambda entrypoint to provided.al2023/
      # arm64 and zips it into modules/compute/build/ — proves the build
      # path actually works, not just that the Go code compiles for the
      # host OS/arch, and satisfies filebase64sha256's real-file
      # requirement before validate runs below.
      - run: make build-lambda
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"
      # No AWS credentials configured — this only checks the HCL itself
      # parses/type-checks. Never `plan` or `apply`.
      - working-directory: ticket-booking/infra/terraform/envs/local
        run: |
          terraform init -backend=false
          terraform validate
```

**Q:** How do you validate every module and root in one command, and why commit the lock file?

**A:** Streampulse's `make tf-validate` runs `terraform fmt -recursive -check` and then loops `init -backend=false` plus `validate` over every module and both roots, using a local provider cache so it works offline after the first init. I commit the lock file only for the two roots, because it pins the exact provider build and hashes, and state and `.terraform` are git-ignored because state can contain secrets. It is a local check, not a CI job in that repo.

**Source:** `streampulse/Makefile:223-226`
```make
tf-validate: ## fmt + validate every Terraform module and env (offline after the first init)
	cd $(TF_DIR) && terraform fmt -recursive -check
	@set -e; for d in modules/kinesis modules/dynamodb modules/s3 modules/sqs modules/iam modules/msk modules/vpc modules/eks envs/validate envs/local; do \
	  echo "== $$d"; (cd $(TF_DIR)/$$d && TF_PLUGIN_CACHE_DIR=$(CURDIR)/$(TF_DIR)/.terraform-plugin-cache terraform init -backend=false -input=false >/dev/null && terraform validate); done
```

**Follow-up they will ask:** "How would you add a guardrail like log retention and an error alarm for a function?"

**A:** I would make the log group explicit so retention is set instead of the default never-expire group, and add an alarm on the Lambda `Errors` metric. This snippet is not from my repo, but I ran `terraform validate` and `fmt -check` on it in a scratch directory with the AWS provider 6.x and placeholder credentials. That proves syntax and references only, and a real apply would still need an SNS action and a real account.

**Illustrative (not from the repo):**

```hcl
resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.function_name}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
```

## Phase 4 — Secrets and least-privilege IAM

### 🟢 Beginner

**Q:** What is least privilege, and how does a Lambda get AWS permissions?

**A:** Least privilege means each identity gets only the actions it needs on only the resources it touches. A Lambda gets permissions from its execution role, which it assumes automatically, so I never put long-lived AWS keys in the code. In my webhook module the role has only the AWS-managed VPC access policy, because the receiver calls no AWS API. That is the smallest grant I could justify from reading the code.

**Q:** Why not just put the secret in the code or in a config file?

**A:** Because code and config files end up in git, in logs and on laptops, and rotating a secret would require a redeploy. I generate the secrets with Terraform's `random_password` and store them in Secrets Manager. I also have to be honest that the value still reaches the function as an environment variable, which is the weakness I discuss at the senior level.

### 🟡 Intermediate

**Q:** How do you decide what an IAM policy should contain?

**A:** I derive it from the code: I list the SDK calls a service actually makes and grant only those actions on only those resources. In streampulse the archive compactor calls list, get, put and delete on S3 objects, so its policy lists exactly those actions, with `s3:ListBucket` on the bucket and object actions scoped to `tenant=*` keys. The file marks each policy as verified from code or unverified, and the unverified ones say so in their description. The mapping from SDK call to IAM action is from the AWS documentation as I remembered it, and the file itself tells me to verify it.

**Source:** `streampulse/infra/terraform/modules/iam/main.tf:30-42`
```hcl
data "aws_iam_policy_document" "archive_compactor" {
  statement {
    sid       = "ListArchive"
    actions   = ["s3:ListBucket"]
    resources = [var.archive_bucket_arn]
  }

  statement {
    sid       = "ReadWriteDeleteArchiveObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.archive_bucket_arn}/tenant=*"]
  }
}
```

**How to talk about it:** Stress the verified-or-unverified labelling, because a policy that looks right is not evidence it is right. Be ready to say the policies are defined but not evaluated, since the emulator does not enforce IAM.

**Q:** Show the Lambda role and secret for the webhook receiver.

**A:** The role trusts only the Lambda service and carries the managed policy for logs and network interfaces. The webhook secret is generated by `random_password`, stored in a Secrets Manager secret, and an operator copies it into the vendor's webhook settings. The invoke permission for API Gateway is scoped to the single route path rather than a wildcard.

**Source:** `GolangExercise/offline-sync-app/infra/terraform/modules/webhook/main.tf:13-17`
```hcl
# The only grant (logs + VPC ENIs): the binary calls no AWS API, its secrets arrive as env vars.
resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.webhook.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}
```

**Source:** `GolangExercise/offline-sync-app/infra/terraform/modules/secrets/main.tf:20-33`
```hcl
# The external system must hold the same value: an operator copies it from this secret into the vendor's webhook settings.
resource "random_password" "webhook" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "webhook" {
  name = "${var.name_prefix}/webhook-secret"
}

resource "aws_secretsmanager_secret_version" "webhook" {
  secret_id     = aws_secretsmanager_secret.webhook.id
  secret_string = random_password.webhook.result
}
```

**How to talk about it:** Say "this is the smallest grant I could justify, and here is the weakness". Then go straight to the senior answer instead of waiting to be asked.

### 🔴 Senior

**Q:** Your webhook secret ends up in a Lambda environment variable. Defend it or fix it.

**A:** I would defend it as a conscious simplification, and name the weakness first. The design doc states the trade-off: anyone with `lambda:GetFunctionConfiguration` can read environment variables, and the stronger option is a `GetSecretValue` call at cold start with one IAM grant, which I did not build to keep a single pattern, the same one the database password already uses. I also found three further gaps when I re-read my own code. First, `DATABASE_URL` is built with the password interpolated into it, so the password is in the environment and in Terraform state too. Second, the comment in the secrets module says the password is never in state, but a `random_password` result is stored in state, so verify that against the provider docs before repeating either claim. Third, the compute role grants `secretsmanager:GetSecretValue`, yet a search of my Go code finds no Secrets Manager call, so that grant is unused permission, which is the opposite of least privilege. None of this was tested against a real account, and rotation is not implemented, since the receiver has one secret and no dual-verify window.

**Source:** `GolangExercise/offline-sync-app/infra/terraform/modules/webhook/main.tf:37-42`
```hcl
  environment {
    variables = merge(var.base_environment, {
      EXTERNAL_SYSTEM = var.system
      WEBHOOK_SECRET  = var.webhook_secret
    })
  }
```

**Source:** `GolangExercise/offline-sync-app/infra/terraform/modules/compute/main.tf:25-46`
```hcl
# Least-priv beyond the managed policy: only the secret this function needs,
# only the photos bucket's objects (PutObject for presigning, GetObject for
# confirm's HeadObject check — s3:GetObject also covers HeadObject).
resource "aws_iam_role_policy" "lambda_app" {
  name = "${var.name_prefix}-lambda-app-policy"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.db_secret_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${var.photos_bucket_arn}/*"
      },
    ]
  })
}
```

**Follow-up they will ask:** "How would you prove the policies are actually least privilege?"

**A:** I would not trust my reading of the code, and I would test it in a real account. The usual tools are the IAM policy simulator, Access Analyzer, and a policy generated from CloudTrail activity, but I have not used any of them on this stack, so verify their current behaviour in the AWS docs. In ADR-0019 I recorded that an emulator does not enforce IAM, so an apply against moto cannot show a denied call. Separately, in `ticket-booking` the seven functions share one execution role scoped to the resources they collectively touch, and the Terraform comment itself says one role per function would be stricter and is future work.

**Q:** How would a customer-facing connector handle secrets differently from your lab setup?

**A:** I would never read a customer credential from an environment variable in a shared function, and I would fetch it at runtime from a secret store, scoped per tenant. I would cache it in memory for a short time, log only a secret's name and never its value, and support rotation with two valid values during a window. My agent console and webhook receiver do not do per-tenant secrets, so this is design reasoning, not something I built.

## Phase 5 — CI/CD (eval gates, test pipelines, what runs where)

### 🟢 Beginner

**Q:** What does your CI pipeline do on a pull request?

**A:** For FieldSync it builds the Go code, runs `go vet` and `go test`, builds the web app, and runs `terraform validate`. The workflow is limited to `offline-sync-app/**` so unrelated changes in the monorepo do not trigger it. It has no deploy step, on purpose, because real AWS access was never approved. I have not seen these jobs run on GitHub's runners, so I describe what the files do, not a run history.

**Q:** Why does CI cross-compile for linux/arm64 if it never deploys?

**A:** Because the Lambda target is `provided.al2023` on arm64, and a build for my laptop's OS does not prove the Lambda binary builds. The step writes to `/dev/null`, so it is a pure compile check. It catches a platform-specific import before it becomes a failed deploy.

### 🟡 Intermediate

**Q:** Show me the Go job and explain each step.

**A:** The job checks out the code, takes the Go version from `go.mod` so CI cannot drift from the module, then runs build, vet and test, and finally the arm64 cross-compile. Each step fails for a real reason, which matters more to me than having many steps. The weak spot is that there is no lint step and no race detector run, and I have not added coverage reporting.

**Source:** `GolangExercise/.github/workflows/fieldsync-ci.yml:17-31`
```yaml
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: offline-sync-app/go.mod
      - run: go build ./...
      - run: go vet ./...
      - run: go test ./...
      # Cross-compile check only — proves cmd/lambda still builds for the
      # provided.al2023/arm64 target the compute Terraform module deploys.
      # Not wired to any deploy step.
      - run: GOOS=linux GOARCH=arm64 go build -o /dev/null ./cmd/lambda
```

**How to talk about it:** Say what each step guards against, and volunteer the missing steps before they ask.

**Q:** What are the two eval gates, and what runs where?

**A:** `agent-eval` is deterministic: it runs pytest and a golden trajectory suite with a scripted fake model and no network, so it can gate a pull request reliably. `eval-gate` has two tiers: a free parity check that fails if the eval prompt drifts from the prompt the server ships, and a model tier that installs Ollama on the runner, pulls two small models and runs promptfoo. The workflow comment says the model tier can be red for an expected reason, so I read the output instead of trusting the badge. The honest status is that `agent-eval` was run step by step on Python 3.12 in Docker and not on GitHub's runners, and `eval-gate` passes locally while my study guide records it as not yet run on a real runner, so verify that before citing it.

**Source:** `AI/.github/workflows/agent-eval.yml:12-26`
```yaml
jobs:
  deterministic:
    name: pytest + golden trajectory suite (no model)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: agent-lab
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest
      - run: python -m evals deterministic
```

**Source:** `AI/.github/workflows/eval-gate.yml:22-37`
```yaml
jobs:
  parity:
    name: prompt parity (no model, seconds)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 evals/ci/check-parity.py

  eval:
    name: promptfoo eval (local Ollama)
    runs-on: ubuntu-latest
    needs: parity
    steps:
```

**How to talk about it:** Lead with the two-tier idea: a cheap deterministic gate that always blocks, and an expensive model gate whose red result needs a human read. Do not say either has gated a real merge.

### 🔴 Senior

**Q:** Where would an eval gate help a customer deployment, and where would it hurt?

**A:** It helps when it is cheap, deterministic and tied to the exact artifact that ships, which is why my parity check derives the rules from the server's real prompt and fails if the eval prompt lacks one. That check exists because on 2026-09-07 the "must decline" case failed in the harness while the server answered correctly, and the cause was two different prompts. A model-based gate hurts when it is slow, flaky or unpinned: mine installs Ollama with `curl | sh` and runs `npx promptfoo@latest`, so a new release could change results without any change in my repo. A failed assertion makes promptfoo exit with code 100, which I verified locally, so a red case fails the job, and that is a measured fact about the tool, not about model quality. The boundary is that I have never seen this gate block a merge in anger, so I would not claim it as an operating practice.

**Source:** `AI/.github/workflows/eval-gate.yml:54-62`
```yaml
      - name: Run promptfoo eval
        working-directory: evals
        run: npx --yes promptfoo@latest eval --no-cache

      # promptfoo exits 100 on any failed assertion (verified locally 2026-09-07),
      # so a red case above already fails this job — nothing further to gate on.
      # A red run here is not automatically a merge-blocker: read the failure.
      # If it's the documented "1B model occasionally invents syntax" case,
      # that's real information about the model, not the harness.
```

**Follow-up they will ask:** "How would you pin and speed up the model tier?"

**A:** I would pin the promptfoo version and the Ollama install, cache the model files between runs, and run the model tier on a schedule or a label instead of every pull request. The deterministic tier would stay as the required check. I have not done this, so I would present it as the next change, not as current state. A path filter also deserves a caution: if a required check never runs because the changed files do not match its paths, the pull request can wait on that check, which you may want to verify in GitHub's current docs.

**Q:** Design the deploy half you deliberately left out.

**A:** I would keep pull request jobs read-only and add a separate deploy workflow on the main branch that authenticates to AWS with OIDC, so there are no stored long-lived keys. It would run `terraform plan`, save the plan, and apply that saved plan behind a protected environment that needs approval. The trade-off is slower deploys in return for a reviewable, reproducible change. The workflow below is illustrative: I checked that it parses as YAML, but I never ran it against a real account, and the role ARN is a placeholder.

**Illustrative (not from the repo):**

```yaml
name: deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/gha-deploy
          aws-region: us-east-1
      - run: make build-lambda
      - working-directory: infra/terraform/envs/prod
        run: |
          terraform init -input=false
          terraform plan -input=false -out=tfplan
      - working-directory: infra/terraform/envs/prod
        run: terraform apply -input=false tfplan
```

**Follow-up they will ask:** "Why apply a saved plan instead of running apply directly?"

**A:** Because what was reviewed is exactly what runs, and nothing drifts between the review and the apply. Plan and apply can sit in one job, and I would split them across an approval gate only if a human must approve in between. In a real setup I would also run the plan step on pull requests with a read-only role. My own repos have no `envs/prod` and no remote state, so this is a design, not a reference to code I wrote.

**Q:** What does your Java project's CI add that the Go one does not?

**A:** Streampulse CI adds a concurrency group that cancels an in-progress run when new commits land on the same ref, a 20 minute job timeout, a formatting check, and test and coverage artifacts uploaded with `if: always()` so I get the reports precisely when tests fail. The file also states its own rule: a pipeline nobody trusts is worse than none, so every step must fail for a real reason. It has no Terraform step, although the header says Terraform validate would arrive later, so that stays a local `make tf-validate`.

**Source:** `streampulse/.github/workflows/ci.yml:18-27`
```yaml
# Cancel an in-progress run when new commits land on the same branch.
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Build & test
    runs-on: ubuntu-latest
    timeout-minutes: 20
```

## Phase 6 — Observability (structured logs, metrics, traces, health checks, error surfacing to a customer)

### 🟢 Beginner

**Q:** What are logs, metrics and traces, and when would you use each?

**A:** Logs are timestamped records of events, metrics are numbers aggregated over time such as error rate and latency, and traces follow one request across services. I use metrics to notice a problem, logs to find what happened in a specific request, and traces to see where time went across services. In my work the Go agent console writes structured JSON logs, streampulse exposes Prometheus metrics through Micrometer, and I wrote an OpenTelemetry collector config for traces. No service ever sent a trace, which I come back to below.

**Q:** What is a health check, and what should it report?

**A:** A health check is an endpoint that tells a platform whether to send traffic to an instance. A liveness answer says the process is up, and a readiness answer says it can do its job, which includes reaching its dependencies. My `/healthz` reports dependency health on purpose, because a server that is up but cannot reach its model should not say "ok" and hide the outage.

### 🟡 Intermediate

**Q:** Walk me through your health handler.

**A:** It builds a status object with the provider, model and whether retrieval is enabled, then, for the Ollama provider only, it probes the model server with a two second timeout. If the probe fails, the status becomes `degraded` with the error and the HTTP code is 503, so a load balancer or monitor can see it. The limit of this design is that one endpoint serves both liveness and readiness, and for any other provider there is no dependency probe at all, so I would split it before putting it behind an orchestrator.

**Source:** `AI/fe-hands-on/server/stream.go:245-274`
```go
func (s *Server) HandleHealth(w http.ResponseWriter, r *http.Request) {
	status := map[string]any{
		"status":    "ok",
		"provider":  s.cfg.Provider,
		"model":     s.cfg.ChatModel,
		"retrieval": s.retriever != nil,
	}
	if r, ok := s.retriever.(*memoryRetriever); ok && r != nil {
		status["chunks"] = r.Len()
	}

	code := http.StatusOK
	if s.cfg.Provider == "ollama" {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, s.cfg.OllamaURL+"/api/tags", nil)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			status["status"], status["error"] = "degraded", err.Error()
			code = http.StatusServiceUnavailable
		} else {
			resp.Body.Close()
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(status)
}
```

**How to talk about it:** Lead with the idea in the doc comment: dependency health is not process liveness. Then admit the single endpoint and the Ollama-only probe before they find them.

**Q:** How do your logs let someone debug one request?

**A:** The logger is the standard library `slog` with the JSON handler, and the chat handler derives a child logger carrying fields such as question length and turn count, then adds retrieval count and retrieval latency as it learns them. On completion it logs prompt tokens, completion tokens and latency in milliseconds. On failure it distinguishes a client that hung up, which it only logs, from a real generation failure, which it logs as an error and also reports in the stream. The gap is that there is no request or correlation id in these lines, and I have not shipped them to any log backend.

**Source:** `AI/fe-hands-on/server/stream.go:221-239`
```go
	u, err := s.provider.Stream(ctx, buildMessages(chunks, req.Messages), emit)
	if err != nil {
		// A cancelled context means the client hung up; there is nobody left to
		// send an error frame to, so just record it.
		if r.Context().Err() != nil {
			log.Info("client disconnected", "err", err)
			return
		}
		log.Error("generation failed", "err", err)
		writeEvent(w, flusher, streamEvent{Type: "error", Value: err.Error()})
		return
	}

	log.Info("chat completed",
		"prompt_tokens", u.PromptTokens,
		"completion_tokens", u.CompletionTokens,
		"latency_ms", u.LatencyMs)

	writeEvent(w, flusher, streamEvent{Type: "done", Usage: &u})
```

**How to talk about it:** Say "one child logger per request, fields added as they become known". Then offer the correlation id as the missing piece, which sets up the senior question.

### 🔴 Senior

**Q:** What does the customer see when your service fails, and is that acceptable?

**A:** Today it is not good enough, and I can show why. When retrieval fails, the handler refuses to degrade into an ungrounded answer, which is the correct decision, and it sends an error frame with the text "retrieval unavailable:" followed by the raw error string. The generation-failure path also sends `err.Error()` to the client. That is helpful for me and wrong for a customer, because it can leak internal hostnames or driver messages and gives the customer nothing to quote to support. What I want is a stable, safe message and a correlation id that appears both in the response and in the log line, so a ticket id leads to exactly one log entry. The snippet below is illustrative and not in my repo; I compiled it and its test passes in a scratch module, where the test asserts the response hides the cause and that the id links to the log. I have not wired it into the agent console.

**Source:** `AI/fe-hands-on/server/stream.go:197-203`
```go
		if err != nil {
			// Retrieval failure must not silently degrade into an ungrounded
			// answer — that is the confident-hallucination path. Fail loudly.
			log.Error("retrieval failed", "err", err)
			writeEvent(w, flusher, streamEvent{Type: "error", Value: "retrieval unavailable: " + err.Error()})
			return
		}
```

**Illustrative (not from the repo):**

```go
type problem struct {
	Error         string `json:"error"`
	CorrelationID string `json:"correlation_id"`
}

func withErrorSurface(log *slog.Logger, next func(http.ResponseWriter, *http.Request) error) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := newID()
		start := time.Now()
		w.Header().Set("X-Correlation-ID", id)
		if err := next(w, r); err != nil {
			log.Error("request failed", "correlation_id", id, "path", r.URL.Path, "err", err.Error(), "ms", time.Since(start).Milliseconds())
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadGateway)
			_ = json.NewEncoder(w).Encode(problem{Error: "upstream unavailable, retry shortly", CorrelationID: id})
			return
		}
		log.Info("request ok", "correlation_id", id, "path", r.URL.Path, "ms", time.Since(start).Milliseconds())
	})
}
```

**Follow-up they will ask:** "For a connector that syncs a customer's Jira, what else do you surface?"

**A:** I surface per-item failures, not just one big error, because a sync that fails one record out of ten thousand should say which record and why. My FieldSync design counts a message that keeps failing, moves it to a dead-letter table with the raw payload, reason and attempts, and keeps the queue moving. What I did not build is alerting on dead-letter growth or replay tooling, and the doc says so. The log lines in that path carry the delivery id, but the SQS consumers use plain `log.Printf` lines, not structured fields, which I would change first.

**Q:** How do you alert on a service level objective without paging on every blip?

**A:** I use multiwindow, multi-burn-rate alerts, where a page needs both a long window and a short window above the threshold, so it fires on a sustained burn and clears soon after the problem ends. In streampulse the fast-burn rule compares the one hour and five minute error ratios with 14.4 times the 0.1 percent budget, and every alert carries a runbook link. The honest status is that these SLO numbers are targets, the rule tests exist but my phase notes record that `promtool` had never been run on them, and that `make up-obs` did not load the rules. So I describe these as drafts, and you should verify the current state of the repo before repeating it.

**Source:** `streampulse/docker/observability/rules/streampulse-alerts.rules.yml:16-27`
```yaml
      - alert: IngestAvailabilityFastBurn
        expr: |
          sp:ingest_error_ratio:rate1h > (14.4 * 0.001)
          and
          sp:ingest_error_ratio:rate5m > (14.4 * 0.001)
        labels:
          severity: page
          slo: ingest-availability
        annotations:
          summary: "Ingest is spending 2% of its 30-day error budget per hour"
          description: "5xx ratio on POST /v1/events:batch over 1h is {{ $value | humanizePercentage }} (target budget 0.1%)."
          runbook: "docs/runbook.md#ingest-5xx-or-503-spike"
```

**Follow-up they will ask:** "And traces?"

**A:** I wrote an OpenTelemetry collector config with a traces pipeline to Tempo, a logs pipeline to Loki and a memory limiter first, and deliberately no metrics pipeline because Micrometer already feeds Prometheus. No service attached the Java agent, so no trace has been produced, and I will not say I have distributed tracing. The next step is to attach the agent to one service, send one request and look for the span in Tempo, which is an experiment I have not run.

**Source:** `streampulse/docker/observability/otel/collector.yaml:35-44`
```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc/tempo]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_http/loki]
```

**Q:** What would you alarm on for the Lambda stack you wrote?

**A:** In `ticket-booking` the observability module turns log lines into metrics with metric filters and alarms on them, and it alarms when any consumer dead-letter queue has a visible message, since that means five real delivery attempts failed. It also has alarms for saga compensations, RDS Proxy session pinning and Redis evictions, plus a dashboard. The conflict-rate alarm is openly a placeholder with an absolute threshold of 1000 until a ratio expression is checked against real traffic. All of it is validated HCL, never applied, so I cannot tell you whether the thresholds are right.

**Source:** `GolangExercise/ticket-booking/infra/terraform/modules/observability/main.tf:98-112`
```hcl
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each            = var.consumer_dlq_names
  alarm_name          = "${var.name_prefix}-${each.key}-dlq-nonempty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "${each.key}'s DLQ has messages — something failed 5 real delivery attempts (docs/plan.md's maxReceiveCount)."
  alarm_actions       = [local.alarm_topic_arn]
  treat_missing_data  = "notBreaching"
}
```

## Phase 7 — Containers and local parity (Docker, compose)

### 🟢 Beginner

**Q:** Why do you use Docker Compose for local development?

**A:** Compose starts the real dependencies the app needs, such as Postgres, with one command, so I do not install them on my laptop and every run starts from the same versions. In FieldSync it starts Postgres 16, a Cognito emulator, MinIO for S3 and a moto server, and `make compose-up` wraps it. Streampulse uses profiles so nothing starts unless I ask for it, because the whole estate would use about 8 to 10 GB of RAM by its own comment. I use compose for dependencies, and I run my own code on the host.

**Q:** What is a health check in compose for?

**A:** It lets compose and the tests know when a dependency is actually ready, not merely started. My Postgres service runs `pg_isready` every 5 seconds with 10 retries. Without it, a test can start before the database accepts connections and fail for a reason unrelated to my code.

### 🟡 Intermediate

**Q:** Show me your local AWS substitutes and a choice you had to change.

**A:** I tried LocalStack first and replaced it, because its image refused to start without an auth token, which the compose comment says I verified directly, so I used MinIO for S3 and moto for the other AWS-style APIs. The Go client targets a custom endpoint with path-style addressing, so the swap needed no Go changes. The weak point is that the FieldSync compose file uses unpinned `latest` tags for MinIO and moto, which makes it non-reproducible, and the streampulse file says explicitly that tags are pinned for that reason.

**Source:** `GolangExercise/offline-sync-app/docker-compose.yml:45-50`
```yaml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: localdevuser
      MINIO_ROOT_PASSWORD: localdevpassword
```

**Source:** `streampulse/docker/compose.yml:32-42`
```yaml
  moto:
    image: motoserver/moto:5.2.2       # `latest` was a 5.2.3.dev build; 5.2.2 verified with `docker manifest inspect`
    profiles: [core]
    container_name: sp-moto
    ports:
      - "5001:5000"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:5000/moto-api/')\" || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10
```

**How to talk about it:** Say the pinned version in streampulse is the pattern I would carry back to FieldSync. Mention that the emulators are permissive, so they are evidence about wiring, not about AWS behaviour.

**Q:** How do you keep an observability stack separate from the base compose file?

**A:** I use a second compose file that adds services and extends two existing ones, then start both files with a profile. The comment points out that relative paths resolve against the first file's directory, which is an easy mistake. Traces and logs live in container filesystems, so `down` loses them. I also have to say that when I last read my phase notes, the Makefile target did not load this override.

**Source:** `streampulse/docker/observability/compose.obs.yml:15-30`
```yaml
services:
  # Every service sends OTLP here: 4317 gRPC, 4318 HTTP. Services run on the host, so both are
  # published. Config is validated with `otelcol-contrib validate` (see README.md).
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.162.0
    profiles: [obs]
    container_name: sp-otel-collector
    command: ["--config=/etc/otelcol/config.yaml"]
    ports:
      - "4317:4317"
      - "4318:4318"
    volumes:
      - ./observability/otel/collector.yaml:/etc/otelcol/config.yaml:ro
    depends_on:
      - tempo
      - loki
```

**How to talk about it:** Present it as the "compose merge" pattern, then be upfront that the wiring was drafted and not run end to end.

### 🔴 Senior

**Q:** What is in your container image recipe, and what have you verified about it?

**A:** The Dockerfile builds one image recipe for every Spring Boot service, extracts the jar into layers so a code-only rebuild re-ships a few kilobytes instead of tens to hundreds of megabytes, runs as a numeric non-root user so a kubelet can verify it, and keeps the application files root-owned so the process cannot rewrite its own code. It sets the heap to 75 percent of the container limit instead of a fixed `-Xmx`, and exits on out-of-memory so the orchestrator restarts it rather than leaving it in an undefined state. The reasoning is in the file's own comments. What I have not verified is a built image: I have no recorded `docker build` of it in the milestones, the ADR it cites is not in the ADR folder, and the layer-size claim is the comment's, not my measurement. So I present this as a reviewed recipe.

**Source:** `streampulse/deploy/docker/Dockerfile:15-33`
```dockerfile
FROM ${JRE_IMAGE}
# Numeric ids: the kubelet can only verify runAsNonRoot against a numeric USER.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
# Root-owned and read-only to the app user: the code a process runs is not writable by that process.
COPY --from=extract /build/extracted/dependencies/ ./
COPY --from=extract /build/extracted/spring-boot-loader/ ./
COPY --from=extract /build/extracted/snapshot-dependencies/ ./
COPY --from=extract /build/extracted/application/ ./

# Heap is a percentage of the container limit, never a fixed -Xmx that can exceed it. 75 leaves room
# for metaspace, thread stacks and direct buffers; a service with native stores (RocksDB) lowers it.
# ExitOnOutOfMemoryError: die and be restarted rather than limp on in an undefined state.
# Set through JAVA_TOOL_OPTIONS so the chart can override it without a shell in the entrypoint.
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75.0 -XX:+ExitOnOutOfMemoryError"

USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Follow-up they will ask:** "Does local parity extend to Lambda?"

**A:** Only partly, and I would say where it stops. At the HTTP layer the same router runs locally and in the Lambda adapter, and CI cross-compiles for linux/arm64, so the code path and the build target are checked. Compose does not run the Lambda runtime, so cold start, the execution role, VPC networking and the real event payloads are not reproduced, and emulators do not enforce IAM. My Lambdas ship as zip files on `provided.al2023`, not as container images, and I did not use the Lambda runtime interface emulator. If I needed closer parity I would add that emulator or a container-image deployment, and I would still treat a real staging account as the only real test.

**Source:** `GolangExercise/offline-sync-app/Makefile:48-52`
```make
build-lambda:
	GOOS=linux GOARCH=arm64 go build -o infra/terraform/modules/compute/build/bootstrap ./cmd/lambda
	cd infra/terraform/modules/compute/build && zip -q -X bootstrap.zip bootstrap
	GOOS=linux GOARCH=arm64 go build -o infra/terraform/modules/eventing/build/photo-processor/bootstrap ./cmd/photo-processor-lambda
	cd infra/terraform/modules/eventing/build/photo-processor && zip -q -X bootstrap.zip bootstrap
```

**Q:** How is your Spring Cloud Function shaped, and has it run on Lambda?

**A:** The compactor is a plain `java.util.function.Function` with a request in and a report out, with no framework type in the signature, so it runs in-process and in tests. The Gradle file says plainly that it has never been deployed as a real serverless function and that a Lambda adapter would be a deploy-time concern not added here. The design behind it, in ADR-0020, writes, re-reads, commits a manifest and only then deletes inputs, so a crash at any point is recovered without duplicates; its tests prove that against objects the tests generate, and the ADR admits no service writes this archive.

**Source:** `streampulse/functions/archive-compactor/src/main/java/com/streampulse/compactor/adapter/in/CompactArchiveFunction.java:12-29`
```java
/** The Lambda-shaped entry point: a request in, a report out, no framework type in sight. */
public final class CompactArchiveFunction implements Function<CompactionRequest, CompactionReport> {

    private final Compactor compactor;

    public CompactArchiveFunction(Compactor compactor) {
        this.compactor = compactor;
    }

    @Override
    public CompactionReport apply(CompactionRequest request) {
        if (request == null) {
            return compactor.compact(Scope.all());
        }
        TenantId tenant = isBlank(request.tenant()) ? null : new TenantId(request.tenant());
        LocalDate date = isBlank(request.date()) ? null : LocalDate.parse(request.date());
        return compactor.compact(Scope.of(tenant, date));
    }
```

**Source:** `streampulse/functions/archive-compactor/build.gradle.kts:1-8`
```kotlin
// ============================================================================
//  archive-compactor — a Lambda-shaped function that compacts the raw archive.
//
//  A Spring Cloud Function `java.util.function.Function` registered in the function
//  catalog. It runs in-process and in tests; it has NEVER been deployed as a real
//  serverless function (ADR-0020). The Lambda adapter would be a deploy-time
//  concern and is not added here.
// ============================================================================
```

**Follow-up they will ask:** "Would you pick Lambda for the compactor?"

**A:** It is a reasonable fit for a periodic job per partition, but the limits decide it. The work is bounded by the Lambda timeout and the ephemeral disk, so I would plan for one partition per invocation and resumable runs, and I would check the maximum timeout and `/tmp` size in the current AWS docs before sizing. I have no measurement of how long a real partition takes, because no real data was ever written to the archive. A JVM with Spring also pays a heavier cold start than my Go binaries, which I have not measured either.

## Code reference index

| path:lines | what it shows |
|---|---|
| `GolangExercise/ticket-booking/cmd/server-lambda/main.go:23-45` | Pool built once in init(), handler only calls the adapter, no defer Close() |
| `GolangExercise/ticket-booking/cmd/saga-worker-lambda/main.go:24-36` | Scheduled one-shot Lambda opening and closing its pool per invocation |
| `GolangExercise/ticket-booking/infra/terraform/modules/compute/main.tf:13-24` | Per-function memory, timeout and reserved concurrency of 50 on the write path |
| `GolangExercise/offline-sync-app/infra/terraform/modules/eventing/main.tf:36-44` | SQS queue with DLQ redrive after 5 receives and a 30 second visibility timeout |
| `GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda/main.go:20-37` | Testable adapter constructor, setup in main not init |
| `GolangExercise/offline-sync-app/cmd/lambda/main.go:36-52` | What a Lambda entrypoint leaves out: no EnsureBucket, unreachable /ws |
| `GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda/main_test.go:57-85` | Synthetic API Gateway v2 events: 202, base64 body, 401, 404 |
| `GolangExercise/offline-sync-app/infra/terraform/envs/local/main.tf:15-26` | Placeholder provider config so validate needs no credentials |
| `GolangExercise/offline-sync-app/infra/terraform/envs/local/main.tf:149-159` | Webhook module wiring, one system variable driving route and env |
| `streampulse/infra/terraform/envs/validate/main.tf:1-12` | Validate-only root that must never be planned or applied |
| `GolangExercise/.github/workflows/fieldsync-ci.yml:47-64` | Terraform validate job with a single placeholder zip |
| `GolangExercise/.github/workflows/ticketing-ci.yml:53-74` | Terraform validate job that builds all Lambda zips first |
| `streampulse/Makefile:223-226` | tf-validate over every module and root with a plugin cache |
| `streampulse/infra/terraform/modules/iam/main.tf:30-42` | Compactor policy derived from the SDK calls the code makes |
| `GolangExercise/offline-sync-app/infra/terraform/modules/webhook/main.tf:13-17` | Webhook role with only the managed VPC access policy |
| `GolangExercise/offline-sync-app/infra/terraform/modules/secrets/main.tf:20-33` | random_password stored in Secrets Manager for the webhook |
| `GolangExercise/offline-sync-app/infra/terraform/modules/webhook/main.tf:37-42` | Webhook secret passed as an environment variable |
| `GolangExercise/offline-sync-app/infra/terraform/modules/compute/main.tf:25-46` | Inline policy granting GetSecretValue and S3 object actions |
| `GolangExercise/.github/workflows/fieldsync-ci.yml:17-31` | Go build, vet, test, and arm64 cross-compile check |
| `AI/.github/workflows/agent-eval.yml:12-26` | Deterministic agent suite as a gating job |
| `AI/.github/workflows/eval-gate.yml:22-37` | Parity tier and model tier with needs: parity |
| `AI/.github/workflows/eval-gate.yml:54-62` | promptfoo run and the note on exit code 100 |
| `streampulse/.github/workflows/ci.yml:18-27` | Concurrency cancel and job timeout |
| `AI/fe-hands-on/server/stream.go:245-274` | Dependency-aware health handler returning 503 when degraded |
| `AI/fe-hands-on/server/stream.go:221-239` | Per-request structured logging and client-gone handling |
| `AI/fe-hands-on/server/stream.go:197-203` | Retrieval failure surfaced loudly, with the raw error text |
| `streampulse/docker/observability/rules/streampulse-alerts.rules.yml:16-27` | Multiwindow burn-rate page with a runbook link |
| `streampulse/docker/observability/otel/collector.yaml:35-44` | Traces to Tempo and logs to Loki pipelines |
| `GolangExercise/ticket-booking/infra/terraform/modules/observability/main.tf:98-112` | Alarm on any visible message in a consumer DLQ |
| `GolangExercise/offline-sync-app/docker-compose.yml:45-50` | MinIO as the S3 stand-in, unpinned image |
| `streampulse/docker/compose.yml:32-42` | Pinned moto image with a healthcheck |
| `streampulse/docker/observability/compose.obs.yml:15-30` | Compose override adding the collector under a profile |
| `streampulse/deploy/docker/Dockerfile:15-33` | Non-root, layered, heap-percentage image recipe |
| `GolangExercise/offline-sync-app/Makefile:48-52` | Cross-compile and zip step that Terraform depends on |
| `streampulse/functions/archive-compactor/src/main/java/com/streampulse/compactor/adapter/in/CompactArchiveFunction.java:12-29` | Lambda-shaped function with no framework types |
| `streampulse/functions/archive-compactor/build.gradle.kts:1-8` | Statement that it was never deployed as a real function |
| `GolangExercise/offline-sync-app/docs/two-way-sync.md:100-121` | Deploy-as-Lambda section: flow, IAM, secret trade-off, verified and not verified |

## Self-check

1. **Q:** Where does expensive setup belong in a Lambda, and what is the cost of doing it wrong? **A:** It belongs in start-up code outside the handler so warm invocations reuse it, and doing it per request pays the cost every time and can exhaust database connections.
2. **Q:** What does `terraform validate` prove, and what does it not? **A:** It proves the configuration parses, types and references correctly, and it does not prove AWS accepts the values, IAM allows the calls, or the plan is what I intend.
3. **Q:** What is the real weakness of the webhook secret handling? **A:** The secret reaches the function as an environment variable that anyone with `lambda:GetFunctionConfiguration` can read, and rotation is not implemented.
4. **Q:** Which of your CI workflows have run on GitHub's runners? **A:** I have no record of any of them running there, `agent-eval` was run step by step in Docker, and my local reproduction shows the `fieldsync-ci` Terraform job would fail on a clean checkout.
5. **Q:** What should the customer see when a request fails? **A:** A stable, safe message and a correlation id that also appears in the log line, not the raw internal error, which is what my agent console currently sends.

## What not to claim

- Do not say any of this was deployed to or applied against a real AWS account; Terraform was validated only, and streampulse's `envs/local` was applied only to an emulator.
- Do not quote cold-start, latency or throughput numbers for the Lambdas; none was measured, and 50 reserved concurrency is a design value.
- Do not say the webhook secret is protected beyond Secrets Manager storage; it is an environment variable, and the database password is too.
- Do not say Terraform state never holds the generated passwords; a `random_password` result lives in state, so verify and correct the comment in `modules/secrets` first.
- Do not say a drained, end-to-end pipeline runs in AWS; the inbox worker is not deployed, so the receiver Lambda would fill `webhook_inbox` and nothing would drain it.
- Do not say CI is green or has gated a merge; there is no run history on record, and the `fieldsync-ci` Terraform job fails on a clean checkout in my local reproduction.
- Do not say `eval-gate.yml` has run on a real runner, or that `agent-eval.yml` has; the latter was run step by step on Python 3.12 in Docker.
- Do not claim distributed tracing, working SLO alerts or tested alert rules; no service attaches the OTel agent, and `promtool` had not been run on the rule tests when I last read my notes.
- Do not claim least privilege has been proven; emulators do not enforce IAM, and one policy grants an action the code never calls.
- Do not claim the container image was built, or that the Spring compactor ever ran as a Lambda; neither is on record.
- Do not state AWS limits (15 minute maximum timeout, memory range, concurrency quota, API Gateway timeout, SQS visibility guidance) as certain; verify them in the current AWS docs.
