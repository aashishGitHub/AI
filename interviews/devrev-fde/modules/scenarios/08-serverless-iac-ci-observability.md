# Scenarios 08 — Serverless, IaC, CI/CD & observability

Real-time situations for [module 08](../08-serverless-iac-ci-observability.md). Each one is a deployment or operations problem an FDE (Forward Deployed Engineer, the person who makes the product work inside one customer's tool estate) meets when shipping and running connectors on serverless platforms.

Lanes: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only. Nothing here was ever applied to a real AWS account: Terraform was validated only, streampulse's `envs/local` was applied only to the moto emulator, no Lambda ran on AWS, and I have no CI run history from GitHub's runners. Every number in a **Situation** is an invented example. AWS limits and log formats are from memory, so verify them in the current AWS docs before quoting. Relative links reach sibling repos, so they resolve only with the same checkout layout as my laptop. I do not paste Couchbase monorepo code.

Ladder: 🟢 scenarios 1-2, 🟡 scenarios 3-4, 🔴 scenarios 5-6.

---

## Scenario 1 — CI passes on my laptop and fails in the pipeline 🟢

**Situation.** Monday 11:20. A pull request that only changes Terraform for the webhook module is red on the `terraform-validate` job, while `terraform validate` is green locally (example). The log ends with an error about a missing file under a module's `build` directory (example).

**Level.** 🟢 Beginner.

**What's being tested.** The difference between your machine and a clean runner: hidden state such as build artifacts, tool versions and credentials.

**Clarifying questions to ask first.**
1. What is the first error line in the job log, and which module does it name?
2. Does the failing module reference a file produced by a build step (a zip hashed with `filebase64sha256`)?
3. What do the local machine and the runner have that differs: the Terraform version, the provider cache, previously built artifacts?
4. Does the workflow build the artifacts before validate, or only create a placeholder?
5. Does the job have credentials, and does it need any?

**Flow of control and data.**

```
laptop:  make build-lambda --> zips exist in modules/*/build --> terraform validate passes
runner:  clean checkout --> one placeholder zip created --> other modules hash a missing zip --> validate fails
fix:     build every zip first (like the ticketing workflow does) --> validate
```

**Diagnosis steps.**
1. Read the first failing line of the job log, not the last. It names the module and the missing path.
2. Search the failing module for `filebase64sha256` or `file(` to find the file it expects on disk.
3. Compare the workflow steps with the Makefile: which zips does `make build-lambda` create that CI never creates?
4. Compare tool versions: the workflow pins Terraform 1.9.0 and the local version differs (mine was 1.14.2).
5. Reproduce in a fresh clone with no build directories. That is the real test.

**Fix now vs fix properly.**
- Now: have the job run the same build step as local (`make build-lambda`) before `terraform init` and `validate`, or create a placeholder for every module that hashes a zip.
- Properly: one command that CI and developers both run, the same tool versions pinned in both places, and a fresh-clone dry run for any workflow change.

**How you'd test it.** A clean-clone run of the exact workflow commands is the test that catches it. My own reproduction on a clean copy of the tree, recorded in the module, showed that the `fieldsync-ci` job creates one placeholder zip while the eventing, websocket and webhook modules hash their own zips, so as written that job would be red. I have no GitHub Actions run history for either workflow, so check the Actions tab before claiming either is green.

**Spoken answer (60-90 seconds).**
"I would assume the runner is the honest one, because a clean runner has only what the workflow creates. So I read the first error in the job log, and here it names a missing file in a module's build directory. That tells me Terraform is hashing a Lambda zip that the pipeline never built. Locally I had run the build, so the zips existed. In my own repo I found exactly this: the fieldsync workflow creates one placeholder zip, but the eventing, websocket and webhook modules also hash their own zips, so on a clean checkout validate would fail. The ticketing workflow avoids it by running the real build step first. The fix is to run the same build in CI as locally, pin the same Terraform version in both, and prove it with a fresh clone. I should be honest that this came from my own local reproduction and I have no record of those workflows running on GitHub's runners."

**Follow-ups the interviewer will ask.**
- Why does validate need real files? `filebase64sha256` reads the file at plan or validate time, so a missing path is an error.
- Why cross-compile for linux/arm64 in CI if you never deploy? To prove the Lambda binary builds on its target, not just on the laptop OS.
- A required check that never runs because of path filters? The pull request can wait forever on it; verify GitHub's current behavior.

**Tie to your code.** [L] The job with one placeholder zip: [fieldsync-ci.yml](../../../../../GolangExercise/.github/workflows/fieldsync-ci.yml). The job that builds all zips first: [ticketing-ci.yml](../../../../../GolangExercise/.github/workflows/ticketing-ci.yml). Build step: [Makefile](../../../../../GolangExercise/offline-sync-app/Makefile).

---

## Scenario 2 — The Terraform plan shows a destroy 🟢

**Situation.** Wednesday 15:40. A pull request that renames a module shows in the plan: `aws_db_instance.main must be replaced` with `-/+` next to it, and the reviewer asks if it is safe to merge (example). The database holds customer data.

**Level.** 🟢 Beginner.

**What's being tested.** Reading a plan, knowing what forces replacement, and refusing to apply a destroy of stateful infrastructure.

**Clarifying questions to ask first.**
1. Which attribute does the plan say forces replacement, or is it a rename that changed the resource address?
2. Is the resource stateful (a database, a bucket, a queue with messages)?
3. Is there a recent backup or snapshot, and is deletion protection on?
4. Does the state match reality, and is the state backend locked and shared?
5. Who approves, and what exactly gets applied: this plan or a fresh one?

**Flow of control and data.**

```
terraform plan --> diff of desired config vs state vs real world
   rename a module/resource --> new address --> plan: destroy old + create new
   fix: moved block (or state mv) tells Terraform it is the same object --> plan: no change
apply the SAVED reviewed plan, never a fresh one
```

**Diagnosis steps.**
1. Read the plan line that explains it: the `# forces replacement` marker names the attribute, and a destroy plus create of the same type usually means an address change.
2. Compare old and new resource addresses in the diff.
3. Check `lifecycle` settings: is `prevent_destroy` set on the resource?
4. Check that a snapshot exists before anything touches a database.
5. Run the plan again from a clean checkout against the real state to confirm it is reproducible.

**Fix now vs fix properly.**
- Now: do not apply. Add a `moved` block (or use `terraform state mv`) so Terraform treats the rename as the same object, then re-plan until the diff is empty.
- Properly: require plan review on every pull request with a read-only role, apply the saved plan from a protected branch behind an approval, set `prevent_destroy` on stateful resources, and add a check that fails the pipeline on any destroy of a protected type.

**How you'd test it.** A plan in CI that must show zero destroys for a rename, checked by reading the plan output. I have not built that. My repos validate only: there is no plan against a real account, and the streampulse ADR records that a second plan against the moto emulator was not empty (3 resources with in-place changes), which it attributes to moto not returning tags and re-serializing JSON. So I have seen a non-empty plan from an emulator, but never a real destroy.

**Spoken answer (60-90 seconds).**
"I would not apply it, and I would say that out loud. A plan that destroys and recreates a database is the plan telling me it thinks the old object and the new one are different things. So I read why: the replacement marker names the attribute, or if I only renamed a module the resource address changed, and Terraform treats a new address as a new resource. For a rename the fix is a moved block, or a state move, so Terraform sees the same object, and I re-plan until the diff is empty. Before touching anything stateful I would check there is a snapshot and that deletion protection or prevent_destroy is set. In a real pipeline I would run the plan on the pull request with a read-only role, review it, and apply the saved plan from a protected branch, so what was reviewed is exactly what runs. I should be honest about my experience: I have validated my Terraform but never applied it to a real account, so this is the process I would follow, not one I have run."

**Follow-ups the interviewer will ask.**
- Why apply a saved plan? Nothing can drift between the review and the apply.
- What does `terraform validate` prove? That the configuration parses, types and references correctly; it does not show that AWS accepts the values or that IAM allows the calls.
- Where should state live? A remote backend with locking and encryption, because state can hold secret values; I did not set one up.

**Tie to your code.** [L] Validate-only provider block: [main.tf](../../../../../GolangExercise/offline-sync-app/infra/terraform/envs/local/main.tf). Validate-only root that must never be planned or applied: [main.tf](../../../../../streampulse/infra/terraform/envs/validate/main.tf). A destroy-guard check, saved-plan apply and a remote backend: [K], not built.

---

## Scenario 3 — The sync Lambda times out mid-run 🟡

**Situation.** Tuesday 13:05. A scheduled extraction Lambda ends with `Task timed out after 60.01 seconds` (example) after a 2.8 s cold start (example). Half of a page was written. The queue message that triggered it reappeared and a second invocation started while the first was still running (example).

**Level.** 🟡 Intermediate.

**What's being tested.** Designing long work to fit a hard time limit: a time budget, checkpoints, idempotent writes, and matching the queue's visibility timeout to the function timeout.

**Clarifying questions to ask first.**
1. What is the configured timeout and memory, and what is the typical page duration?
2. Is the work triggered by a schedule or by a queue message, and what is the queue's visibility timeout?
3. Does the job write a checkpoint after each page, and are writes idempotent?
4. What did the invocation spend its time on: cold start, a slow vendor, a `Retry-After` sleep?
5. Is a second concurrent invocation safe, or does the design assume one runner?

**Flow of control and data.**

```
invoke --> init (cold start) --> loop: if time left < safety margin: stop, save cursor
                                  fetch page --> apply page + checkpoint in one transaction
hard kill at the limit --> no cleanup runs --> only the last committed checkpoint survives
queue: visibility timeout expires while the first run lives --> message redelivered --> overlap
```

**Diagnosis steps.**
1. The platform's per-invocation report line: duration, billed duration, max memory, and an init duration on a cold start. Duration pinned at the timeout confirms it hit the limit.
2. The Duration metric (p99) against the configured timeout over the last day.
3. The sync state row: is the cursor advancing between runs, or is the same page repeating?
4. The queue's receive count and the visibility timeout against the function timeout. Equal values allow a duplicate delivery while the first run is alive.
5. Where the time went: the log line before the kill, a rate-limit sleep, or a slow upstream call.
6. Dead-letter queue depth, to see whether redeliveries are exhausting their attempts.

**Fix now vs fix properly.**
- Now: shrink the page size or raise the timeout modestly, and raise the queue's visibility timeout above the function timeout.
- Properly: check the remaining time before each page with a safety margin sized to the slowest page, save the cursor after each applied page, keep writes idempotent so a replay is a no-op, bound any `Retry-After` wait, and ensure only one runner at a time (advisory lock or a single scheduled invocation).

**How you'd test it.** A unit test with a fake clock showing the loop stops before a page it cannot finish and resumes from the checkpoint (`TestRun_StopsBeforeAPageItCannotFinishAndResumesFromTheCheckpoint`), and an integration test that crashes on page 2 and resumes with zero duplicates (`TestIntegration_CrashMidBackfillResumesFromCheckpointWithZeroDuplicates`). Neither ran inside a real Lambda deadline, and I have not measured real page times or cold starts.

**Spoken answer (60-90 seconds).**
"A hard timeout is a kill with no cleanup, so the design has to assume it will happen. First I would read the invocation report to see whether the time went to the cold start, the vendor or a rate-limit sleep, and check whether the sync cursor is advancing between runs. Then I would fix the design, not just raise the timeout. The job should check the time left before each page and stop cleanly with a saved cursor if the next page might not finish, with the margin sized against the slowest page. Each page and its checkpoint commit together, so a kill replays at most one page, and the write is version-gated so the replay changes nothing. The duplicate invocation points at the queue: if the visibility timeout equals the function timeout, the message becomes visible again while the first run is still alive. I would make it larger than the function timeout, and I would verify the recommended multiple in the AWS docs. My extractor is built this way but I never ran it inside a real Lambda deadline, so I have no measured numbers."

**Follow-ups the interviewer will ask.**
- What if one page takes longer than the margin? The margin is wrong and the hard kill wins; treat it as a tunable measured against the slowest page.
- How does this map to DevRev? Their worker has a soft timeout capped at ten minutes and a hard kill at 1.3 times that, and it should check `isTimeout` between pages; verify the current docs.
- Why is a duplicate delivery survivable? The consumer checks a processed-events table before running the handler.

**Tie to your code.** [L] Budget check and checkpoint: [extractor.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/extractor.go). Queue with 30 s visibility timeout and DLQ redrive: [main.tf](../../../../../GolangExercise/offline-sync-app/infra/terraform/modules/eventing/main.tf). Consumer-side dedupe before the handler runs: [sqsconsume.go](../../../../../GolangExercise/offline-sync-app/internal/sqsconsume/sqsconsume.go). A deadline-aware loop sketch (not in the repo): module 08, Phase 1.

---

## Scenario 4 — A secret is readable from the function configuration 🟡

**Situation.** Wednesday 10:00. During a customer security review, a contractor role with read access to Lambda configuration can see `WEBHOOK_SECRET` in plain text in the function's environment variables (example). The reviewer asks whether anyone could forge webhook deliveries.

**Level.** 🟡 Intermediate.

**What's being tested.** Secret handling trade-offs, rotation without dropping deliveries, least privilege, and honest incident scoping.

**Clarifying questions to ask first.**
1. Who holds `lambda:GetFunctionConfiguration`, and has anyone actually read it (CloudTrail)?
2. Is the same secret reused anywhere else, and is it also in Terraform state or logs?
3. What does the secret protect: forging deliveries, and what would a forged delivery cost?
4. Can the vendor send signatures from two secrets during a rotation window?
5. What else sits in the environment: the database URL with its password?

**Flow of control and data.**

```
Terraform: random_password --> Secrets Manager secret --> operator copies to vendor
                           \--> Lambda env var WEBHOOK_SECRET (readable via GetFunctionConfiguration)
rotation: accept signatures from OLD and NEW for an overlap window --> vendor switches --> retire OLD
better:   Lambda fetches the secret at cold start (GetSecretValue, one IAM grant), caches in memory
```

**Diagnosis steps.**
1. Audit log for reads of the function configuration by that role in the exposure window.
2. Verifier outcomes: count `bad_signature` rejections. A leaked secret yields valid signatures, so the clue is unusual delivery ids, sources or timing, not rejections.
3. Check where else the value lives: Terraform state (a generated password is stored there), CI logs, the database URL in the environment.
4. Review the role policies: in my build the compute role grants `secretsmanager:GetSecretValue` but a search of the Go code finds no Secrets Manager call, so that grant is unused permission.
5. Check the replay window and body cap, which bound what a captured request can do.

**Fix now vs fix properly.**
- Now: rotate. Generate a new secret, accept both old and new signatures for an overlap window without returning early on the first match, update the vendor, then retire the old one. Restrict who can read function configuration.
- Properly: fetch the secret at cold start from Secrets Manager with one scoped grant, cache it briefly in memory, never log values, remove unused grants, encrypt and lock remote state, and move to per-tenant secrets for a customer-facing connector. Rotation is not built in my repo.

**How you'd test it.** A unit test that a delivery signed with either the old or the new secret verifies during the overlap and that only the new one verifies after, plus a test that a wrong secret returns 401 and stores nothing (that last one exists: `TestHandler_BadSignatureIs401AndNothingStored`). The dual-secret test and the Secrets Manager fetch are not built: [K].

**Spoken answer (60-90 seconds).**
"I would scope it before I fix it. The secret protects against forged deliveries, so the question is whether anyone who could read it did, and for that I would check the audit log for reads of the function configuration and look for unusual deliveries, remembering that a forged delivery with the right secret passes verification, so rejections will not show it. Then I would rotate. The safe way is an overlap window where the receiver accepts signatures from both the old and new secret, with a loop that does not return on the first match, so I do not drop real deliveries and I do not leak which secret matched. I would then retire the old one. For the permanent fix I would fetch the secret from Secrets Manager at cold start with one scoped permission instead of using an environment variable. In my own build the secret is an environment variable, there is no rotation, the database URL embeds the password, and one role has an unused GetSecretValue grant. I would say all of that plainly, because it is cheaper than the reviewer finding it."

**Follow-ups the interviewer will ask.**
- Is the secret really absent from Terraform state? No: a generated password is stored in state, so the comment in my secrets module that implies otherwise needs correcting; verify against the provider docs.
- How would a per-tenant connector differ? Fetch each tenant's credential at runtime from a secret store, cache briefly, log only names, and support two valid values during rotation.
- Can you prove least privilege? Not with an emulator, which does not enforce IAM; I would use the policy simulator or access analysis in a real account and verify current behavior in the AWS docs.

**Tie to your code.** [L] Secret passed as an env var: [main.tf](../../../../../GolangExercise/offline-sync-app/infra/terraform/modules/webhook/main.tf). Generated secret in Secrets Manager: [main.tf](../../../../../GolangExercise/offline-sync-app/infra/terraform/modules/secrets/main.tf). Inline policy with the unused grant: [main.tf](../../../../../GolangExercise/offline-sync-app/infra/terraform/modules/compute/main.tf). Dual-secret verification is a sketch in the module, not built: [K].

---

## Scenario 5 — The alert fires at 3 a.m. and there is no runbook 🔴

**Situation.** Friday 03:12. A page fires: `IngestAvailabilityFastBurn` (example). Its annotation links to `docs/runbook.md#ingest-5xx-or-503-spike`. The on-call opens it and finds no such file. The customer's own users see an error message with raw internal text and no id to quote.

**Level.** 🔴 Senior.

**What's being tested.** Incident handling and observability maturity: mitigate first, alert quality (burn rates), runbooks as tested artifacts, correlation ids, and what the customer sees.

**Clarifying questions to ask first.**
1. What does the alert actually measure, and over which windows? Is it a real user-facing SLO breach?
2. What changed in the last hour: a deploy, a config change, a dependency incident?
3. Is there a safe fast mitigation: roll back, fail over, scale, disable a feature flag?
4. Can I tie a customer's error to one log line? Is there a correlation id?
5. Who owns the alert, and who must be told at what severity?

**Flow of control and data.**

```
metric: 5xx ratio 1h and 5m --> both > 14.4 x 0.1% budget --> page (severity: page, runbook link)
on-call: ack --> dashboards --> /healthz (dependency probe, 503 when degraded) --> logs by correlation id --> mitigate
customer sees: stable message + correlation_id  (today: raw error text, no id)
```

**Diagnosis steps.**
1. Acknowledge, open the dashboard and compare the 1 hour and 5 minute error ratios, to see whether the burn is current and sustained.
2. Check the last deploy and config change times against the start of the burn.
3. Call the health endpoint: a degraded dependency should return 503 with the failing component.
4. Pull logs for the failing path and group by error. Without a correlation id, a customer ticket cannot be tied to one line.
5. Check tracing: in my build no service attached the OpenTelemetry agent, so no trace exists and I cannot claim distributed tracing.
6. Check each alert's runbook link actually resolves. When I searched the streampulse tree I found no `runbook.md`, though the rules reference one; verify before repeating.

**Fix now vs fix properly.**
- Now: mitigate (roll back the last change, restore the dependency, or fail over) and tell the customer the window. Write the missing runbook after the incident, from what you just did.
- Properly: every alert gets a runbook that exists, with a CI check that every `runbook:` annotation resolves; rule unit tests run with `promtool` (my notes record it had never been run); a correlation id returned in the response and written to the log line; a stable, safe customer message instead of the raw error; and tracing actually attached to one service.

**How you'd test it.** A test that parses the alert rules and asserts each runbook path and anchor exists would have caught the missing file. It is not built. Alert rule tests exist but `promtool` had not been run on them when I last read my notes. For the error surface, a test that the response hides the cause and that the correlation id links to the log line passed in a scratch module only, not in the agent console.

**Spoken answer (60-90 seconds).**
"At 3 a.m. the first job is to mitigate, not to diagnose beautifully. I would acknowledge, look at the one-hour and five-minute error ratios to confirm it is a current, sustained burn, and check what changed in the last hour, then roll back or restore the dependency. My fast-burn alert fires only when both windows exceed 14.4 times the 0.1 percent budget, which is why it pages on a real burn and clears soon after it ends. The runbook it links to does not exist in my repo, as far as I could find. That is a process bug, and the fix is a check in CI that every runbook annotation resolves. The second gap is the customer side: my console sends the raw error text, which can leak internal details and gives the customer nothing to quote. I would return a stable message and a correlation id that is also in the log line. I should be honest that my SLO numbers are targets, the rule tests had not been run with promtool, and no service ever produced a trace."

**Follow-ups the interviewer will ask.**
- Why multiwindow, multi-burn-rate? A page needs both a long and a short window above threshold, so it fires on a sustained burn and resets quickly, without paging on every blip.
- Liveness versus readiness? Liveness says the process is up; readiness says it can do its job including its dependencies; my single health endpoint serves both, and I would split it before an orchestrator.
- What does a connector surface per item? Which record failed and why, with failed records moved to a dead-letter table, not one big error.

**Tie to your code.** [L] Burn-rate alert rules: [streampulse-alerts.rules.yml](../../../../../streampulse/docker/observability/rules/streampulse-alerts.rules.yml). Dependency-aware health handler and the raw-error response: [stream.go](../../../../fe-hands-on/server/stream.go). The OTel collector config with no producer: [collector.yaml](../../../../../streampulse/docker/observability/otel/collector.yaml). The missing runbook file and the annotation-resolves check: [K].

---

## Scenario 6 — Everything is green but nothing is syncing 🔴

**Situation.** Friday 16:00. The customer says no updates have reached DevRev since Tuesday. The receiver's dashboard looks healthy: zero Lambda errors, API responses are 202, latency is normal (example). The inbox table holds 18,000 rows (example) and every row has `processed_at` unset. This is a hypothetical for the design as written, since the receiver was never deployed.

**Level.** 🔴 Senior.

**What's being tested.** Silent failure: a stage that succeeds while the next stage does not exist. Alerting on end-to-end freshness (age of the oldest unprocessed item) instead of per-stage errors.

**Clarifying questions to ask first.**
1. Which components run in each runtime: where does the inbox worker run, and is it deployed at all?
2. What does "healthy" mean on the dashboard: errors and status codes, or end-to-end lag?
3. How old is the oldest unprocessed inbox row, and is the backlog growing linearly?
4. Is there a dead-letter queue or dead-letter table with content?
5. Does the receiver have a concurrency cap, and what protects the database if the vendor floods it?

**Flow of control and data.**

```
vendor --> API Gateway --> receiver Lambda --> INSERT webhook_inbox --> 202     (green: no errors)
                                                  |
                                       worker runs ONLY inside cmd/webhook-receiver (not deployed)
                                                  X nothing drains the inbox --> backlog grows, lag grows
```

**Diagnosis steps.**
1. Age and size of the backlog: `SELECT count(*), min(received_at) FROM webhook_inbox WHERE processed_at IS NULL AND dead_at IS NULL`. A large count with an old minimum confirms nothing is draining.
2. Outcome counts: `SELECT outcome, count(*) FROM webhook_inbox GROUP BY outcome`. All NULL or zero processed means the worker is not running.
3. Which runtimes host the worker, extractor and loader: in my build they run as ticker loops in one process, and only the receiver has a Lambda.
4. The dead-letter table: empty confirms it is a missing drainer, not poison messages.
5. The receiver's metrics: errors are zero and success is high, which is exactly why a per-stage dashboard is green.
6. Concurrency settings on the receiver: none reserved in my design, so a flood would also hit the database.

**Fix now vs fix properly.**
- Now: start a worker against the inbox (a scheduled invocation or a container) and drain in small batches. Applying is version-gated, so order and replays are safe. Tell the customer the window and run a poll catch-up.
- Properly: make the worker queue-triggered and deploy it with the receiver as one unit, alarm on the age of the oldest unprocessed row and on dead-letter depth, add a retention job for the inbox, cap receiver concurrency, and add a deploy smoke test that posts a signed event and waits for it to be processed.

**How you'd test it.** A post-deploy smoke test: send one signed delivery, then poll until its inbox row is processed within a set time, and fail the release otherwise. Not built. Today `go test ./cmd/webhook-receiver-lambda` proves the adapter returns 202 and stores a row, which is exactly the half that works. My doc states that deployed alone, the receiver would fill the inbox and nothing would drain it.

**Spoken answer (60-90 seconds).**
"This is the scariest kind of failure because every stage you are watching is succeeding. The receiver's job is to verify, store and answer 202, and it does that perfectly, so errors are zero and latency is fine. What is missing is the next stage. In my design the inbox worker, the extractor and the loader run as ticker loops inside one local process, and only the receiver has a Lambda, so deployed alone it would fill the inbox and nothing would drain it. My own docs list that as not solved. To diagnose I would ignore the receiver dashboard and look at freshness: how many inbox rows are unprocessed and how old the oldest is, and whether the dead-letter table is empty, which tells me it is a missing drainer and not poison messages. The immediate fix is to run a worker and drain in small batches, which is safe because applying is version-gated. The permanent fix is to deploy the worker with the receiver, alarm on the age of the oldest unprocessed item, and add a smoke test that proves an event gets processed. This was never deployed, so it is a design risk, not an incident I lived."

**Follow-ups the interviewer will ask.**
- Why alarm on age and not errors? Errors cover a stage that fails loudly; age covers a pipeline that stops silently.
- What would you alarm on in the Lambda stack? A non-empty consumer dead-letter queue, saga compensations, connection-proxy pinning and cache evictions, as in my ticket-booking module, all validated and never applied.
- Should the receiver have a concurrency cap? Yes, so a vendor flood cannot exhaust the database; reserved concurrency was set on the ticket-booking write path but not on this receiver.

**Tie to your code.** [L] The documented gap: [two-way-sync.md](../../../../../GolangExercise/offline-sync-app/docs/two-way-sync.md). Worker, extractor and loader wired as ticker loops in one process: [main.go](../../../../../GolangExercise/offline-sync-app/cmd/webhook-receiver/main.go). Receiver adapter test: [main_test.go](../../../../../GolangExercise/offline-sync-app/cmd/webhook-receiver-lambda/main_test.go). DLQ-depth alarm (validated HCL, never applied): [main.tf](../../../../../GolangExercise/ticket-booking/infra/terraform/modules/observability/main.tf). The deploy smoke test and the oldest-unprocessed alarm: [K], not built.
