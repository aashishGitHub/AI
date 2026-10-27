# Scenarios 05 — Webhooks & two-way sync

Real-time situations for [module 05](../05-webhooks-and-two-way-sync.md). Each one is a customer problem an FDE (Forward Deployed Engineer, the person who makes the product work inside one customer's tool estate) meets while building a sync like DevRev AirSync (data sync between a customer's tools and DevRev).

Lanes: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only. All **[L]** code here ran against a **mock** Jira (`mockjira`) that I wrote, never a real vendor, and the Lambda was never applied to AWS. Every number in a **Situation** is an invented example, not a measurement. Relative links reach sibling repos, so they resolve only with the same checkout layout as my laptop. I do not paste Couchbase monorepo code.

Ladder: 🟢 scenarios 1-2, 🟡 scenarios 3-4, 🔴 scenarios 5-6.

---

## Scenario 1 — One webhook, six delivery attempts 🟢

**Situation.** Tuesday 02:40 IST. The customer's admin at Acme (example) writes: "Your integration created the same ticket six times." Their vendor delivery dashboard shows delivery `dlv-8841` with attempts 1 to 5 answered `500` and attempt 6 answered `202` (example). Receiver log line (example): `webhook mockjira: persist delivery dlv-8841: connection refused`.

**Level.** 🟢 Beginner.

**What's being tested.** Whether you know the receiver contract: which status codes ask the sender to retry and which stop it, and how dedupe makes a retry harmless.

**Clarifying questions to ask first.**
1. Is `dlv-8841` the same delivery id on all six attempts, or does the vendor mint a new id per retry? (This decides whether my dedupe key works at all.)
2. How many tickets actually exist for that Jira key: one or six?
3. What happened to the database between 02:30 and 02:40: failover, connection limit, deploy?
4. Did the vendor give up on any other delivery after its retry budget, so that events were lost rather than duplicated?
5. Is a poll running underneath as the safety net, and when did it last complete?

**Flow of control and data.**

```
vendor --POST dlv-8841--> verify HMAC --> INSERT webhook_inbox ON CONFLICT DO NOTHING
  attempts 1-5: DB down  -> 500 inbox_unavailable  -> vendor retries
  attempt 6:    DB up    -> 202 accepted (1 row)
worker tick (2 s) --> claim row --> apply --> mark processed (1 work item)
```

**Diagnosis steps.**
1. Vendor delivery log: is the delivery id identical on every attempt? If yes, dedupe covers it.
2. Receiver logs: count the `persist delivery ... inbox_unavailable` lines and the 500 responses in the window. They match attempts 1-5, so the 500s were deliberate retry requests.
3. `SELECT count(*) FROM webhook_inbox WHERE delivery_id = 'dlv-8841'` should return 1, because the primary key is `(system, delivery_id)`.
4. `SELECT outcome, count(*) FROM webhook_inbox WHERE system = 'mockjira' GROUP BY outcome` shows one `applied` for that delivery, not six.
5. Count work items by the external id in `external_id_map` to confirm one link and one item.
6. Database metrics for 02:30-02:40 (connections, failover events) to explain the blip.
7. Compare vendor-side delivery counts with inbox rows for the same hour to find any delivery the vendor abandoned.

**Fix now vs fix properly.**
- Now: show the customer the one inbox row and the one work item, and say the six attempts were the vendor retrying because I asked it to. For any delivery the vendor abandoned, trigger a poll catch-up or the vendor's redeliver button.
- Properly: alert on receiver 5xx rate and on inbox backlog age (neither is built in my repo), keep the poll as the correctness net, and fix whatever made the database unavailable.

**How you'd test it.** `TestHandler_InboxFailureIs500SoSenderRetries` proves a failed insert returns 500, and `TestHandler_DuplicateDeliveryIs202AndStoredOnce` proves a repeat is stored once and answered `202 duplicate`. `TestIntegration_DuplicateDeliveryIsProcessedOnce` proves it end to end on real Postgres.

**Spoken answer (60-90 seconds).**
"First I would check whether it is really six tickets, because I expect it is one. In my receiver the inbox table has the system plus the delivery id as its primary key, and the insert is ON CONFLICT DO NOTHING, so a repeat of the same delivery id cannot create a second row. The five 500s were me asking the vendor to retry: when the database insert fails I return 500 on purpose, because nothing was stored and the sender must try again. The sixth attempt stored the event and got a 202. So I would query the inbox by delivery id, expect one row and one applied outcome, and show the customer that. The two things I would still verify are whether the vendor reuses the delivery id on retries, since a new id per retry would defeat my dedupe key, and whether the vendor gave up on any other delivery after its retry budget. For those I rely on the poll underneath, because webhooks are a fast path and can be lost. Then I would add an alert on the 5xx rate and the inbox backlog age, which my build does not have today."

**Follow-ups the interviewer will ask.**
- What if the vendor mints a new delivery id on every retry? The inbox dedupe misses, but the version gate in apply still makes the replay a no-op because the entity version did not change.
- Why 202 and not 200? The event is accepted and stored, not processed.
- Why not do the work inside the request? The sender's retry policy would then depend on my database and my slowest handler.

**Tie to your code.** [L] Handler status codes and inbox insert: [handler.go](../../../../../GolangExercise/offline-sync-app/internal/webhook/handler.go). Backlog and outcome queries: [two-way-sync.md](../../../../../GolangExercise/offline-sync-app/docs/two-way-sync.md). Alerting on 5xx and backlog age is not built: [K].

---

## Scenario 2 — Two events arrive in the wrong order 🟢

**Situation.** Wednesday 10:15. A support lead at the customer says ticket `MJ-1` shows "In Progress" in DevRev while Jira says "Done" (example). The vendor log shows two deliveries for `MJ-1`: `dlv-1` carries version 2 (status Done) and `dlv-2` carries version 1 (status In Progress), and `dlv-2` arrived second (example). The connector in this scenario is a hypothetical first cut that applies events in arrival order. It is not my repo's behavior.

**Level.** 🟢 Beginner.

**What's being tested.** That you never order events by arrival time or by a wall clock, and that you know what a version gate is.

**Clarifying questions to ask first.**
1. Does the vendor put a monotonic version, revision or `modifiedDate` on each event, and is it per entity?
2. Does the vendor promise any ordering, or only at-least-once delivery?
3. Is this one record or many? One suggests a race, many suggests a systematic design flaw.
4. Which fields are affected: only vendor-owned fields, or also fields that DevRev edits?
5. Is there a poll that would eventually correct the record?

**Flow of control and data.**

```
vendor: v1 sent, v2 sent        network reorders
receiver stores:  dlv-1 (v2)  then  dlv-2 (v1)
apply(v2) -> UPDATE ... SET last_version = 2 WHERE last_version < 2   (1 row, applied)
apply(v1) -> UPDATE ... SET last_version = 1 WHERE last_version < 1   (0 rows -> ignored_stale)
```

**Diagnosis steps.**
1. Inbox rows for the entity: `received_at` and the payload `version` for each delivery, to prove arrival order differs from version order.
2. Outcome column: in a gated design the late v1 shows `ignored_stale`. In the first-cut connector there is no such outcome and both say `applied`.
3. `external_id_map.last_version` for the record against the vendor's current version from a direct GET.
4. Check whether the apply path compares timestamps from the payload (clock skew) or an integer version.
5. Check the poll path: does it apply through the same gate, or write directly?

**Fix now vs fix properly.**
- Now: re-read the record from the vendor and apply it through the gate, so the stale write is overwritten by the true latest.
- Properly: one atomic statement that advances a per-link version only when the incoming version is strictly newer, used by both webhook and poll writers. Equal versions are stale, so a replay is a no-op.

**How you'd test it.** `TestApply_OlderVersionIsIgnoredStaleAndWritesNothing` at unit level, and `TestIntegration_OutOfOrderDeliveryIgnoresTheOlderVersion` on real Postgres, which delivers a pair in reverse order and asserts the old one is ignored.

**Spoken answer (60-90 seconds).**
"I would not trust arrival order, because the network and the vendor's retries can reorder anything. The first question is whether the vendor gives me a monotonic version per record. If it does, the fix is a version gate. In my implementation that is one SQL statement: update the link's last_version to the incoming version where last_version is strictly less than it. If zero rows come back, the event is stale or a duplicate and I label it ignored_stale and write nothing. Both the webhook path and the poll path go through that same gate, so a backfill page can never overwrite a newer webhook. To diagnose this ticket I would line up the two inbox rows by received_at and by version, compare last_version with what the vendor returns now, and then re-apply the latest through the gate. I would not order by timestamps, because clock skew between two machines silently picks the older edit. One honest limit: all of this is tested against my own mock vendor, so I would first check what ordering and version fields the real vendor documents."

**Follow-ups the interviewer will ask.**
- What if the vendor has no version field? Use its modified timestamp as a weaker proxy, accept that ties and skew exist, and lean on a periodic reconcile.
- Why strictly newer, not newer-or-equal? Equal means a replay, and a replay should be a no-op.
- What about a delete that arrives before its create? The delete carries a higher version, so it wins and the late create is stale.

**Tie to your code.** [L] Version gate query `AdvanceLinkVersion`: [queries.sql](../../../../../GolangExercise/offline-sync-app/sqlc/queries.sql) and its caller in [apply.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/apply.go). Portable drill with the `>=` tie rule: [merge_records.py](../../drills/py/fde/merge_records.py).

---

## Scenario 3 — The echo loop doubles every update 🟡

**Situation.** Thursday 14:20. The customer's Jira admin reports that every edit made in DevRev is followed by a second edit by the "DevRev integration" user, and Jira rate limiting (`429`) has started (example). Jira issue `MJ-7` history shows 14 edits in 10 minutes from one human change (example).

**Level.** 🟡 Intermediate.

**What's being tested.** Loop prevention in a two-way sync, and knowing which guard is doing the work.

**Clarifying questions to ask first.**
1. Which fields are editable on both sides, and has anyone changed field ownership recently?
2. Does the vendor stamp the actor or origin on webhook events, and what is the exact format?
3. Did a deploy or config change precede this, for example a changed actor name or a new field mapped?
4. Is the loop one record or many, and does the edit count grow linearly or exponentially?
5. Is the outbound push sending an idempotency key, and is it stable per event?

**Flow of control and data.**

```
user edits in DevRev --> work_item + domain_event (actor = user)
loader --> origin filter (skip actor system:jira) --> PATCH owned fields + Idempotency-Key
vendor applies v+1 --> webhook back --> echo check (version AND content hash) --> echo, stop
   if the echo is not recognized --> apply --> new domain_event --> loader pushes again  (loop)
```

**Diagnosis steps.**
1. Vendor issue history: who made each edit, and the timestamps between them. A fixed small gap suggests an automatic loop.
2. Count loader PATCH calls per internal event id in the logs. The key is the event id, so more than one call per event means retries, and a new event per echo means a loop.
3. Inbox outcomes: `SELECT outcome, count(*) FROM webhook_inbox GROUP BY outcome`. A healthy system shows `echo` outcomes. A loop shows `applied` for events that our own push caused.
4. Check the actor on the domain events produced by apply. The loader skips events whose actor is `system:<sys>`. If apply stopped stamping that actor, the filter no longer fires.
5. Compare the version and content hash stored after the push with the version and content of the returning webhook.
6. Check field ownership: a field owned by both sides removes the strongest guard.
7. Watch `429` counts to confirm the loop is what is exhausting the rate limit.

**Fix now vs fix properly.**
- Now: pause the outbound loader so the loop stops, restore the actor stamp or ownership map that regressed, then resume.
- Properly: keep all three independent guards. Single-writer fields (each field has one owner), the origin filter in the loader, and an echo memory holding the pushed version and content hash. Add a metric on the share of `echo` outcomes and alert when it drops to zero or when push count per event exceeds one.

**How you'd test it.** `TestIntegration_EchoLoopTerminates` drives push then webhook and asserts it ends. Because any one guard ends the loop in the default configuration, that test alone would still pass with the echo memory removed. `TestIntegration_EchoOfAnOlderPushIsNotReportedAsAConflict` is the one that fails without echo memory, and `TestApply_SameVersionButDifferentContentIsNotAnEcho` guards against swallowing a real edit.

**Spoken answer (60-90 seconds).**
"A loop means a change that came from the vendor is being pushed back to the vendor as if it were new. First I would stop the bleeding by pausing the outbound loader, because the loop is also burning the customer's rate limit. Then I would find which guard failed. I use three: each field has exactly one owner, so the vendor's edit to a field it does not own is not applied; the loader drops any event whose actor is the vendor's system user; and I remember the version and content hash that I got back from my own push, so when the webhook returns carrying that same version and hash I label it an echo and touch nothing. For this symptom I would look at the actor on the events and at the inbox outcomes: if I see applied where I expect echo, one of those guards regressed. I would not claim the echo memory is what ends loops, because it overlaps the other two. What it uniquely buys me is not reporting a false conflict when the echo of an older push arrives after a newer local edit, and I have a test for exactly that case."

**Follow-ups the interviewer will ask.**
- How does this map to DevRev's loop prevention? The SDK records `external_versions` after a write and the next import recognizes its own change by version matching; the connector must return the real modified date from the write.
- What about a field both sides can edit? Move to a three-way merge using the last-synced snapshot as the base, and report a conflict when both changed.
- What is the known race? If the webhook is processed before the loader records its push, it is not labelled echo, the merge is a no-op, and the loop still ends.

**Tie to your code.** [L] Origin filter and push: [loader.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/loader.go). Echo check and version gate: [apply.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/apply.go). Field ownership: [ownership.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/ownership.go). Portable drill: [echo_guard.py](../../drills/py/fde/echo_guard.py).

---

## Scenario 4 — The backfill and the live webhooks race 🟡

**Situation.** Thursday 11:00. A first sync of 400,000 tickets (example) started at 05:00 and is still running. The customer notes that several tickets show older titles than Jira, and two work items appear for one Jira key (example). Webhooks have been arriving the whole time.

**Level.** 🟡 Intermediate.

**What's being tested.** Whether every writer funnels through one idempotent, ordered apply, and whether first-sight identity creation is race-safe.

**Clarifying questions to ask first.**
1. Are webhooks enabled during the backfill, or only after it completes?
2. Is one extraction runner active, or could two have started?
3. How is the backfill ordered: by `updated_at`, by id, or by cursor from the vendor?
4. How does the code map external id to internal id, and is it insert-then-select or select-then-insert?
5. Are the stale titles on tickets that were edited during the backfill window?

**Flow of control and data.**

```
extractor page N (rows at version v1) --\
                                         >--> Apply --> ResolveInternalID --> version gate --> work_item
webhook (same row at version v2) -------/
page N+K arrives late with v1 --> gate: 0 rows --> ignored_stale
page + checkpoint commit in ONE transaction; crash replays at most one page
```

**Diagnosis steps.**
1. `SELECT * FROM sync_state`: the in-flight cursor, `run_since`, `run_max`. Is the cursor advancing, or is the same page repeating?
2. Outcome counts split by source: how many `ignored_stale` from poll versus webhook. A healthy race shows poll rows ignored as stale.
3. For five sample stale tickets, compare `external_id_map.last_version` with the vendor's current version. If last_version is lower, the newer event was never applied.
4. Look for two work items with the same external key. That means the identity mapping minted two ids.
5. Check whether the poll writer calls the same Apply as the webhook worker, or has its own write path.
6. Check for two extractor processes (the design assumes one runner).
7. Check `EXTRACT_OVERLAP` (default 5 minutes in my config) against the late-commit pattern.

**Fix now vs fix properly.**
- Now: for each sample record, re-fetch from the vendor and apply it through the gate. If duplicate work items exist, tombstone the loser and repoint the link, after reviewing with the customer.
- Properly: one Apply for every writer; insert-then-select identity mapping with `ON CONFLICT DO NOTHING`; page and checkpoint in one transaction; an advisory lock or single scheduled invocation so only one extractor runs.

**How you'd test it.** `TestIntegration_ConcurrentFirstSightCreatesOneLinkAndOneItem` fires eight concurrent first sights of one external id. `TestIntegration_CrashMidBackfillResumesFromCheckpointWithZeroDuplicates` and `TestIntegration_IncrementalPullIsIdempotentAcrossTheOverlapWindow` cover resume and overlap. I do not have a test that interleaves a webhook between a page fetch and its apply, so the unit-level proof is `TestApply_OlderVersionIsIgnoredStaleAndWritesNothing`, and I would add the interleaving test.

**Spoken answer (60-90 seconds).**
"Two different races are possible here, so I would separate them. The first is stale overwrite: a backfill page carrying version 1 lands after a webhook carrying version 2. In my design both go through the same Apply, which advances a per-record version in one statement and ignores anything not strictly newer, so the late page is labelled ignored_stale. If I see stale titles, that tells me some writer bypassed the gate, and I would look for it. The second race is two first sights of one external id creating two internal records. I handle that with insert first, select second: the insert is ON CONFLICT DO NOTHING on the external key, so the second transaction waits and then reads the winner's id. I have a test with eight concurrent first sights that asserts one link and one item. For the running job I would look at the sync state cursor to confirm it is advancing, make sure only one extractor runs, because my design assumes one runner, and fix the samples by re-fetching from the vendor through the gate. All of this runs against my mock vendor, so throughput at 400,000 tickets is something I have not measured."

**Follow-ups the interviewer will ask.**
- Why check the time left before each page? A page you cannot finish is wasted, and the checkpoint is written with the page, so a kill replays at most one page.
- Does the poll path consult echo memory? No, by design, so a label-only `conflict` can appear while a push is in flight; the data is still correct.
- How would this scale to many tenants? Shard by tenant, one checkpoint per shard, a shared rate limiter in front of the vendor, and accept no ordering across shards.

**Tie to your code.** [L] Resumable extraction: [extractor.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/extractor.go). Identity race test: [integration_test.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/integration_test.go). The interleaving test is not built: [K]. Portable drill: [extractor.ts](../../drills/ts/src/extractor.ts).

---

## Scenario 5 — A delete in the source never reaches the target 🔴

**Situation.** Monday 09:00, quarterly audit. The customer finds 312 tickets in DevRev whose Jira keys return 404 (example). Their Jira admin says the issues were hard-deleted months ago. Nothing in the inbox mentions them (example).

**Level.** 🔴 Senior.

**What's being tested.** Whether you understand that an incremental poll cannot see deletes, what a tombstone is, and what a reconciliation pass is for.

**Clarifying questions to ask first.**
1. Does the vendor soft-delete (a flag) or hard-delete (row gone)? Does it emit a delete webhook, and does its list endpoint ever return tombstones?
2. How long does the vendor retain tombstones? A short retention loses deletes for a poll that lags.
3. Which direction matters: vendor deletes reaching DevRev, or DevRev deletes reaching the vendor?
4. What does the customer want a delete to mean in DevRev: hide, archive or remove?
5. How many records are in scope, and how often can a full id listing run without hitting rate limits?

**Flow of control and data.**

```
vendor hard delete --(no webhook, no tombstone)--> nothing arrives
incremental poll (updated_since) --> returns only changed rows --> a missing row proves nothing
periodic reconcile: list ALL ids + versions from vendor  vs  external_id_map
   missing_internally / behind / orphaned_internally --> act (tombstone orphans after review)
```

**Diagnosis steps.**
1. Take five ghost keys and GET each from the vendor: confirm 404 (hard delete) versus a flagged soft delete.
2. Search the inbox for any event for those keys carrying a delete flag. None means the vendor sent no delete webhook.
3. Check whether the vendor's list endpoint includes tombstones, and for how long.
4. Look at the poll window: `sync_state` watermark and `EXTRACT_OVERLAP`. Late or missed deletes outside the overlap are never seen.
5. Run the id-set comparison offline (vendor ids versus `external_id_map`) to size the problem before changing anything.
6. Check the outbound side: the loader only subscribes to `work_item.updated`, so internal deletes are never pushed.

**Fix now vs fix properly.**
- Now: a reviewed one-off reconcile that tombstones (soft-deletes) the orphans, never hard-deletes, with the list sent to the customer first.
- Properly: use delete webhooks and vendor tombstones where they exist, run a scheduled full reconcile of ids and versions where they do not, keep tombstones versioned so a stale create cannot resurrect a record, and add outbound deletes only after agreeing what a delete means.

**How you'd test it.** `TestIntegration_DeletesAreTombstonesAndAMissingPollRowDeletesNothing` proves a poll with no row deletes nothing and a delete event tombstones the row. `TestIntegration_DeleteArrivingBeforeCreateStillWinsByVersion` proves ordering. A reconcile test (fake vendor ids against fake internal ids asserting the three buckets) is not built: [K].

**Spoken answer (60-90 seconds).**
"A hard delete leaves no event and no row, so an incremental poll can never infer it, and treating a missing row as a delete would be dangerous. In my build a delete is just another change at a higher version: the upsert sets deleted_at and never removes the row, and a late create is ignored as stale so it cannot resurrect the record. That covers vendors that tell me about deletes. For a vendor that hard-deletes silently, the only answer is reconciliation: list all ids and versions from the vendor, compare with my link table, and classify records as missing here, behind, or orphaned here. I have the core of that as a sketch but I have not built or run it in the repo. For the customer's 312 tickets I would confirm with a GET that they return 404, size the set with an offline id comparison, send the list for review, and then soft-delete them. I would also tell them honestly that my outbound direction does not push deletes at all today, and ask what a delete should mean to them before building it."

**Follow-ups the interviewer will ask.**
- Why soft-delete in the target? A reversible tombstone survives a wrong classification, and the version keeps order correct.
- How often would you reconcile? Driven by vendor rate limits and the customer's freshness need; nightly for ids, with a cheap count check more often.
- What if two external ids should be one internal record after a merge? My schema does not support it today; it would be a deliberate migration with the survivor chosen first.

**Tie to your code.** [L] Tombstone upsert (`UpsertWorkItem`): [queries.sql](../../../../../GolangExercise/offline-sync-app/sqlc/queries.sql). Delete tests: [integration_test.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/integration_test.go). Reconciliation is a sketch in the module only, not built: [K].

---

## Scenario 6 — The vendor changes a field type 🔴

**Situation.** Friday 09:15. The vendor shipped an API change overnight: `status` was the string `"Done"` and is now an object `{"name":"Done","id":10001}` (example). The inbox backlog has grown from 0 to 3,400 rows (example) and `sync_dead_letters` is filling. A customer manager asks why no updates have landed since 07:00.

**Level.** 🔴 Senior.

**What's being tested.** Poison-message handling, the value of storing raw bytes before parsing, contract testing against a third party you do not control, and safe replay.

**Clarifying questions to ask first.**
1. Did the vendor announce the change, and is it versioned (can I pin the old shape with a header)?
2. Does the poll path decode the same shape, so is it failing too?
3. Is the new shape a clean replacement or are both shapes in flight?
4. Which fields are required for correctness and which are optional?
5. How many deliveries are already dead-lettered versus still pending?

**Flow of control and data.**

```
vendor (new shape) --> verify --> INSERT raw bytes into webhook_inbox --> 202   (raw event is safe)
worker tick --> claim --> decode FAILS --> attempts+1 --> at max attempts --> sync_dead_letters(raw payload, reason)
fix decoder --> replay dead letters in small batches --> version gate makes replay safe
```

**Diagnosis steps.**
1. Backlog and lag: `SELECT count(*), min(received_at) FROM webhook_inbox WHERE processed_at IS NULL AND dead_at IS NULL`.
2. Dead letters: `SELECT source, attempts, reason, created_at FROM sync_dead_letters ORDER BY created_at DESC`. A decode error repeated across thousands of rows with identical reason text is a systemic change, not a poison message.
3. Pull one raw payload from a dead letter and diff it against a known-good fixture to find the changed field.
4. Check the exact first failing timestamp and correlate it with the vendor's release notes or status page.
5. Check the poll path logs for the same decode error.
6. Confirm the receiver is still answering 202 (events are being stored) so nothing is lost while the decoder is broken.

**Fix now vs fix properly.**
- Now: ship a decoder that accepts both shapes (string or object), stop treating it as poison, and replay the dead letters in small batches with the same backoff rules after confirming the vendor is healthy. Tell the customer the exact window affected.
- Properly: contract tests built from recorded real payloads, tolerant reading of unknown fields and strict checking of required ones, pin the vendor API version if offered, and alert on dead-letter growth. In my build inbox retries have no backoff beyond the tick interval, so a systemic change burns every row's attempts quickly, which is why raw-bytes-first matters.

**How you'd test it.** `TestIntegration_PoisonInboxEventIsDeadLetteredAfterNAttempts` proves a body that will not parse is dead-lettered after exactly N attempts with its raw bytes and that attempts stop growing. A fixture-based contract test that decodes recorded payloads of both shapes is not built: [K].

**Spoken answer (60-90 seconds).**
"The first thing I would confirm is that nothing is being lost. My receiver stores the raw bytes in the inbox and answers 202 before any parsing, so a change in the vendor's payload shape cannot drop events, it can only stop them being applied. The worker then fails to decode, counts attempts, and at the limit copies the row to a dead-letter table with the raw payload and the reason. With a systemic change like this, thousands of rows share one reason string, which tells me it is a contract change, not poison. The fix is a decoder that accepts both shapes, then replaying the dead letters in small batches, which is safe because applying is version-gated. The honest weak spots in my build are that inbox retries have no backoff, so every row burns its attempts within seconds, and I have no alert on dead-letter growth and no contract tests. Those are what I would add first: fixtures recorded from the real vendor, tolerant reading of unknown fields, and an alert so the customer does not find out before we do."

**Follow-ups the interviewer will ask.**
- Is replaying a thousand dead letters safe? For correctness yes, because of the version gate; for load, replay in small batches and confirm the vendor is healthy first.
- How do you separate replayable from not? Record the reason per row; transient causes replay, poison bodies need a code or data fix.
- How would you catch this before production? Recorded-payload fixtures in CI, and a scheduled canary that decodes a live sample from the vendor.

**Tie to your code.** [L] Attempt counting and dead-lettering: [worker.go](../../../../../GolangExercise/offline-sync-app/internal/webhook/worker.go). Dead-letter test: [integration_test.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/integration_test.go). Replay SQL is a sketch only, not built, and contract tests and dead-letter alerts do not exist: [K].
