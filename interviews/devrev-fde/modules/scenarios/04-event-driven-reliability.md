# Scenarios 04 — Event-driven reliability

Source module: [`../04-event-driven-reliability.md`](../04-event-driven-reliability.md). Six real-time situations an FDE meets, laddered 🟢 🟢 🟡 🟡 🔴 🔴.

How to use: read only the **Situation**, answer out loud, then compare. Every number in a Situation is an **example**. Numbers from my repos are marked "from config", "observed once" or "derived", as in the module. I did not run any of these tests while writing this file.

Lanes: **[P]** shipped at Couchbase · **[L]** my own build (FieldSync, ticket-booking, StreamPulse), never deployed to a customer · **[K]** knowledge only, not built. Everything in the repos below is [L].

| # | Level | Failure mode |
|---|---|---|
| 1 | 🟢 | Duplicate side effect after a consumer crashes between the effect and the mark |
| 2 | 🟢 | A poison event is retried forever |
| 3 | 🟡 | A claimed idempotency key swallows the client's retry (silent loss) |
| 4 | 🟡 | Out-of-order application corrupts a read model |
| 5 | 🔴 | The outbox relay is stalled and the database disk is filling with WAL |
| 6 | 🔴 | Consumer lag climbs: store outage or poison record? |

---

## Scenario 1 🟢 Customers got two notifications after a worker restart

**Situation.** Monday 08:50 (example). A work-item consumer was restarted by the platform at 03:12 (example). Afterwards, two customers received the same notification and one work item exists twice. Logs show nothing unusual.

**Level.** 🟢 Beginner.

**What's being tested.** At-least-once delivery, and why the consumer must make a repeat harmless. Where the gap between "side effect done" and "marked processed" lives.

**Clarifying questions to ask first.**
1. Which step is the side effect (email, API call, row insert) and is it idempotent on its own?
2. Where is "processed" recorded, and in the same transaction as the effect?
3. What does the consumer do when it dies between the two?
4. Is the event id available to the downstream system as an idempotency key?

**Flow of control and data.**

```
domain_events ─▶ ListUnprocessedEventsForConsumer (anti-join on processed_events)
   ─▶ handle(evt)  [SIDE EFFECT]  ──── crash window ────▶ MarkEventProcessed(evt, consumer)
next tick: event still unprocessed ─▶ handle(evt) again ─▶ duplicate effect
```

**Diagnosis steps.**
1. Find the event ids behind the duplicate effects and look them up in `processed_events` for that consumer name. A missing row for an event whose effect exists confirms the crash window.
2. Search logs for the same event id handled twice, around the restart time.
3. Check whether the handler is idempotent by itself (upsert on a natural key, or an idempotency key sent downstream).
4. Look at the relay too: publish then mark published also duplicates by design if the process dies in between.

**Fix now vs fix properly.**
- Now: de-duplicate the affected records by event id, and apologise to the two customers.
- Properly: make the handler idempotent on the event id (a dedupe table claimed in the same database transaction as the effect, or an idempotency key to the external system). A claim and an effect only close the gap when they commit together. If the effect is in another system, the key must travel with the call.

**How you'd test it.** A crash-injection test: run the handler, fail at the point after the effect and before the mark, re-run the tick, and assert the effect count is exactly one. In my repo the relay's publish failure path is unit-tested with a fake publisher and gomock, where the absence of an expected `MarkEventPublished` call is the assertion. The mid-gap crash test for the original consumer is not written.

**Spoken answer (60-90 seconds).**
This is at-least-once delivery doing its job, and the bug is that the handler is not idempotent. In my original FieldSync consumer the handler runs first and the event is marked processed in a separate statement afterwards. If the process dies between the two, the next tick selects the event again and the handler repeats. I say that honestly, because it means my handlers must be idempotent on their own. The fix is to key the effect on the event id: either a dedupe table with a primary key of event id and consumer name, claimed in the same transaction as the effect, or, for an external call, an idempotency key sent with the request. My two-way sync loader already uses the event id as that key. For the customer I would write a test that crashes after the effect and before the mark and asserts exactly one effect, because that is the failure that actually happened.

**Follow-ups the interviewer will ask.**
- *Mark first, then act?* Then a crash loses the effect instead of repeating it. At-least-once plus idempotence beats at-most-once for most business events.
- *Can you promise exactly-once?* No. I promise at-least-once plus idempotent processing. Kafka Streams `exactly_once_v2` covers Kafka to Kafka only.
- *Where else can a duplicate enter?* The relay: after `PutEvents` succeeds and before `MarkEventPublished` commits.

**Tie to your code.** [L] [`GolangExercise/offline-sync-app/internal/consume/consume.go`](../../../../../GolangExercise/offline-sync-app/internal/consume/consume.go), [`GolangExercise/offline-sync-app/internal/outbox/relay.go`](../../../../../GolangExercise/offline-sync-app/internal/outbox/relay.go) and [`relay_test.go`](../../../../../GolangExercise/offline-sync-app/internal/outbox/relay_test.go), dedupe queries in [`sqlc/queries.sql`](../../../../../GolangExercise/offline-sync-app/sqlc/queries.sql).

---

## Scenario 2 🟢 The same event fails every 5 seconds for three days

**Situation.** Tuesday 11:00 (example). A support engineer notices the consumer log repeating `handle event <same id> failed, will retry next tick` every few seconds, since Saturday (example). The payload is malformed JSON from a partner. Newer events seem delayed.

**Level.** 🟢 Beginner.

**What's being tested.** Poison messages, retry caps, and telling a bad record from an outage. The difference between code that dead-letters and code that retries forever.

**Clarifying questions to ask first.**
1. Is there an attempt counter or a dead-letter path in this consumer?
2. Is the failure permanent (bad payload) or transient (database blip)?
3. How many events does the consumer take per tick, and how are they ordered?
4. Are newer events actually blocked, or just delayed?

**Flow of control and data.**

```
tick ─▶ list unprocessed (LIMIT 25, ordered) ─▶ handle(evt) ──err──▶ log + continue (NOT marked) ─▶ next tick: same event again
webhook worker: failure ─▶ attempts++ ─▶ attempts >= max ─▶ sync_dead_letters(raw body, reason, attempts) + mark inbox dead
```

**Diagnosis steps.**
1. Group the log lines by event id. One id repeating means a poison record, not an outage.
2. Read the error text. A JSON decode error cannot heal by retrying.
3. Query for unprocessed events for this consumer and count them against the batch limit of 25. My reading, not tested: if 25 or more poison events sit at the head of the ordering, they could occupy the whole batch and starve later events.
4. Check whether the code has any attempt count. In the original consumer it does not.

**Fix now vs fix properly.**
- Now: park the poison event by hand (record it for inspection, then mark it processed), so the consumer moves on.
- Properly: an attempts counter per event, a cap, and a dead-letter table that stores the raw bytes, the reason and the attempt count. Distinguish permanent errors (dead-letter at once) from transient ones (retry with backoff), and never confuse an outage with a bad record. Add a replay tool and an alert on dead-letter growth, which I do not have.

**How you'd test it.** The webhook worker integration test sends a validly signed body of `not json`, asserts exactly 3 attempts, a stored reason and the raw body, and that attempts stop growing afterwards. The same shape of test for the original consumer would fail today, which is the point of writing it.

**Spoken answer (60-90 seconds).**
A repeating line for one event id is a poison message: it can never succeed, so retrying burns capacity. My original FieldSync consumer has this weakness and I say so up front: a failed event is simply not marked processed, so it is retried next tick, with no attempt counter and no dead-letter path. That is fine for a database blip and wrong for a malformed body. The webhook worker I wrote later does it properly: each failure runs in its own transaction, increments an attempts column and stores the last error, and at the configured maximum it inserts a dead-letter row with the raw body as bytes, because a poison body may not be valid JSON, then marks the inbox row dead. The two-way loader splits the decision further: exhausted retries and permanent 4xx responses dead-letter, anything else is returned so the event stays unprocessed. What I have not built is backoff between inbox retries, replay tooling, or an alert on dead-letter growth.

**Follow-ups the interviewer will ask.**
- *Why store raw bytes?* The poison body may not be valid JSON or text.
- *How does the Kafka version differ?* The poison record sits in front of the offset, so without a dead-letter topic one bad record stops its partition (Scenario 6).
- *Where in your code is a bad message dropped silently?* The ticket-booking projector logs and marks malformed events processed. A silent drop with only a log line as evidence.

**Tie to your code.** [L] [`consume.go`](../../../../../GolangExercise/offline-sync-app/internal/consume/consume.go) (retries forever), [`internal/webhook/worker.go`](../../../../../GolangExercise/offline-sync-app/internal/webhook/worker.go) (cap and dead letter), [`internal/twoway/loader.go`](../../../../../GolangExercise/offline-sync-app/internal/twoway/loader.go), tests in [`internal/twoway/integration_test.go`](../../../../../GolangExercise/offline-sync-app/internal/twoway/integration_test.go), gaps in [`docs/two-way-sync.md`](../../../../../GolangExercise/offline-sync-app/docs/two-way-sync.md), silent skip in [`ticket-booking/internal/projector/projector.go`](../../../../../GolangExercise/ticket-booking/internal/projector/projector.go).

---

## Scenario 3 🟡 After a broker blip, events are missing and ingest says "duplicate"

**Situation.** Wednesday 14:03 (example). The message broker was unavailable for about 90 seconds. Ingest returned errors, and clients retried. Dashboards later show a gap for that window, while the ingest counters show a large number of "already seen" events (example). Nothing is in the dead-letter topic.

**Level.** 🟡 Intermediate.

**What's being tested.** An idempotency claim is a reservation, not a record of completion. Compensating actions, and the crash case that no catch block covers.

**Clarifying questions to ask first.**
1. Is the id claimed before the publish or after?
2. If the publish fails, who releases the claim?
3. What is the claim's time to live, and what happens to a retry inside it?
4. What does the system do when the idempotency store itself is down (fail open or closed)?

**Flow of control and data.**

```
client batch ─▶ claim ids in Redis (SET NX EX, key namespaced by tenant)
   ─▶ publish to broker ──ok──▶ 202
                        └─fail─▶ release(claimed ids) ─▶ rethrow ─▶ client retries and is NOT swallowed
process crash between claim and publish ─▶ no release ─▶ retry answered as duplicate for the TTL (24 h, from config)
```

**Diagnosis steps.**
1. Compare events the clients say they sent with events published, for the window. The gap equals the swallowed ids.
2. Read the counters: already-seen count against published count.
3. Check logs for the publish failure and whether the release ran (it is best-effort and never throws).
4. Check whether any process crashed or was killed in the window. A crash skips the release, which is my reading of the code, not something I tested.
5. Check the circuit breaker window. With it open, every batch in the window fails fast, so every batch needs its claims released.

**Fix now vs fix properly.**
- Now: delete the claim keys for the affected window so client retries are accepted, and ask clients to resend. Ids are client-generated, so a resend uses the same ids.
- Properly: a claim state of pending then done, so a pending claim past a timeout can be retried, or downstream deduplication so ingest can safely accept a duplicate. For telemetry, failing open on an idempotency-store outage is a deliberate trade (a duplicate is recoverable, a lost event is not). For payments I would fail closed.

**How you'd test it.** A test where the publisher throws and the retry must be accepted, which also checks the release ran. A test named for the bug, `withoutTheReleaseTheRetryIsSwallowed`, keeps it executable. The crash-between-claim-and-publish case has no test.

**Spoken answer (60-90 seconds).**
My first suspect is the claim, because a claim without a publish turns the client's retry into silent loss. In StreamPulse's ingest I claim each event id in Redis with set-if-absent and a TTL, namespaced by tenant, and then publish. If the publish throws, the service releases the claims before rethrowing, so the client's retry is accepted. The release is best-effort and never throws, so the caller sees the real publish error. A test keeps that bug executable by showing what happens without the release. The case I have not closed is a process crash between the claim and the publish: the release only runs inside the catch block, so the retry would be answered as a duplicate for up to the 24 hour TTL. That is my reading of the code and I have not tested it. The fix is a pending and done claim state, or downstream deduplication. Fixing the immediate gap means deleting the affected keys.

**Follow-ups the interviewer will ask.**
- *Why fail open when Redis is down?* A duplicate inflates a metric and is visible, a gap is permanent. Producer idempotence still stops duplicates from broker retries. The decision lives in a config flag, and ADR-0007 records it.
- *Why must the Redis claim be atomic?* `SET key NX EX` does the test and the set in one server-side step. A null boxed boolean is treated as claimed, because treating it as seen would drop events silently.
- *Any similar pattern elsewhere?* The ticket-booking charge key is a SHA-256 over user, order and hold, stable across retries of one checkout.

**Tie to your code.** [L] [`streampulse/.../IngestService.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java), [`RedisIdempotencyStore.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/redis/RedisIdempotencyStore.java), [`IngestServiceTest.java`](../../../../../streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/application/IngestServiceTest.java), [`ADR-0007`](../../../../../streampulse/docs/adr/0007-fail-open-on-idempotency-store-failure.md).

---

## Scenario 4 🟡 The seat map shows free seats that were held

**Situation.** Thursday 17:20 (example). A read model (a Redis bitset of seat states) disagrees with the database for a busy event. Replaying the events produces fewer applied changes than there are transitions: in my integration test, 220 real held and released transitions produced only 112 applied changes. No errors anywhere.

**Level.** 🟡 Intermediate.

**What's being tested.** Ordering as a correctness property. Why delivery order does not matter to a relay but matters to a projector, and how an idempotency check can hide an ordering bug.

**Clarifying questions to ask first.**
1. Does the consumer's correctness depend on applying transitions in their real order?
2. What column defines the order, and is it a strict total order?
3. What does the consumer do when it sees a transition that looks like a repeat?
4. Is the same ordering used by the relay and the projector?

**Flow of control and data.**

```
seat service ─▶ domain_events (outbox) ─▶ projector: SELECT ... ORDER BY created_at ─▶ apply to Redis bitset
two same-direction transitions applied out of real order ─▶ apply()'s own idempotency check no-ops the second one
fix: ORDER BY outbox_seq (BIGSERIAL assigned at insert time)
```

**Diagnosis steps.**
1. Compare the bitset with the authoritative state in the database for the affected event.
2. Count applied changes against events replayed. A lower count than transitions means some were treated as no-ops.
3. Read the ordering of the query. `created_at` alone is a timestamp, not a strict total order under rapid inserts.
4. Look at which events were no-ops: always the second of two same-direction transitions.

**Fix now vs fix properly.**
- Now: rebuild the bitset from the database for affected events.
- Properly: order by a monotonic sequence assigned at insert time, as the migration did. The same fix is pending elsewhere: my FieldSync relay and consumer queries still order by `occurred_at`. For data where every intermediate state matters, ordering per key with one writer per key.

**How you'd test it.** The overflow integration test that replays real transitions and asserts the applied count. It is the test that found the bug. A mutation: switch the query back to `created_at` and confirm the test fails.

**Spoken answer (60-90 seconds).**
This is an ordering bug disguised as an idempotency feature. My ticket-booking projector applies seat transitions to a Redis bitset, and applying two same-direction transitions out of their real order makes the second one a silent no-op through the projector's own idempotency check. A real integration test in my repo replayed 220 transitions and got only 112 applied changes, which exposed that `created_at` is not a strict total order under rapid inserts. I added a BIGSERIAL `outbox_seq`, assigned at insert time, and the projector orders by it. The relay does not care about delivery order, the projector does, and I wrote that into the query comment. The gap I still have is that my FieldSync relay and consumer queries order by `occurred_at`. I did not demonstrate a bug there, but it is the same weakness. Where I cannot trust ordering, as in a data-layer sync, I use an atomic version gate in SQL that applies an incoming version only if it is strictly newer.

**Follow-ups the interviewer will ask.**
- *Kafka ordering across partitions?* Only within a partition, so key by what needs ordering. StreamPulse keys raw telemetry by `sessionId`: `tenantId` would give three hot partitions, a null key gives no ordering.
- *How can the sink be correct without order?* Its upsert only replaces a row whose stored `computed_at` is older or equal, so reordering and replays cannot move a value backwards. Not suitable for a ledger.
- *Why not just add partitions later?* Raising the partition count rehashes keys and breaks per-key ordering.

**Tie to your code.** [L] [`ticket-booking/sqlc/queries.sql`](../../../../../GolangExercise/ticket-booking/sqlc/queries.sql) (`ListUnprocessedDomainEvents`), [`migrations/000008_domain_events_outbox_seq.up.sql`](../../../../../GolangExercise/ticket-booking/migrations/000008_domain_events_outbox_seq.up.sql), version gate in [`offline-sync-app/sqlc/queries.sql`](../../../../../GolangExercise/offline-sync-app/sqlc/queries.sql), partition keys in [`streampulse/api/asyncapi/streampulse-topics.yaml`](../../../../../streampulse/api/asyncapi/streampulse-topics.yaml).

---

## Scenario 5 🔴 The change-data-capture relay is down, consumers are stale and the database disk is filling

**Situation.** Saturday 03:30 (example). The Kafka Connect worker running the Debezium connector crashed. The control plane still returns 201 and 200. Downstream caches stop updating, with no errors, only staleness. The database disk usage grows (example: 71% to 78% in six hours) and the replication slot shows as inactive.

**Level.** 🔴 Senior.

**What's being tested.** The outbox relay as an operational component: failure modes of CDC, WAL retention by a replication slot, and what an honest runbook and alerting would contain.

**Clarifying questions to ask first.**
1. Is the connector down, paused or failing, and is the slot active?
2. How much WAL is the slot retaining, and how much free disk do we have?
3. Are writes still succeeding and rows accumulating in the outbox table?
4. Is this connector being retired (drop the slot) or just restarted?
5. What are consumers' lag and staleness requirements?

**Flow of control and data.**

```
app tx: business row + outbox row (one transaction) ─▶ Postgres WAL ─▶ replication slot ─▶ Debezium (Connect) ─▶ Kafka topic (compacted)
connector DOWN: slot inactive ─▶ WAL retained for the slot ─▶ disk grows ─▶ (abandoned slot eventually fills the disk)
consumers: lag = staleness, not an error · on restart the connector resumes from the slot, in order (observed once)
```

**Diagnosis steps.**
1. Check the connector and task status through the Connect REST API (verify the endpoint and fields in the current Debezium and Connect docs).
2. Inspect the replication slot view in Postgres: active flag and how far its restart position lags the current WAL position (verify the exact view and columns in the Postgres docs).
3. Check free disk and WAL directory growth.
4. Count outbox rows written since the last record that reached Kafka, to size the backlog.
5. Look at consumer lag per partition on the topic. Staleness with zero errors is the signature.

**Fix now vs fix properly.**
- Now: restart the connector. It resumes from the slot and the records arrive in order, which I observed once by hand. If the connector is retired for good, drop the slot, otherwise the slot keeps WAL forever.
- Properly: alert on slot lag and retained WAL, a connector health alert, a retention job for the outbox table (a gap: none exists), a limit on WAL retained per slot (verify the Postgres setting and its version support), a runbook, and an automated restart test. The polling alternative (as in FieldSync) has no slot, so its stall shows as unpublished rows instead, and the ceiling is throughput.

**How you'd test it.** The CDC integration test covers the happy path against real Postgres, Kafka and Debezium containers (three records on one key, one partition, increasing offsets, a null-value tombstone). The restart and WAL retention behaviour was observed by hand and is not automated. I would add a test that stops Connect, writes rows, restarts it, and asserts order and completeness.

**Spoken answer (60-90 seconds).**
The key thing about a CDC relay is that its failure is silent to the application. In StreamPulse the control plane only inserts the outbox row in its own transaction and Debezium publishes it, so when Connect stopped, I observed that the service kept returning success, outbox rows accumulated, and Postgres kept the write-ahead log for the inactive replication slot. Consumers see staleness, not an error. On restart the connector resumed from the slot and the records arrived in order, which I saw once, by hand. The danger is an abandoned slot that retains WAL until the disk fills, so a retired connector needs the slot dropped. My honest gaps are that I have no alert on slot lag, no retention job on the outbox table, and no automated restart test, and I observed this on one Debezium image tag, so I would re-check behaviour against current docs when upgrading. I chose Debezium over a polling publisher for lower latency, and I recorded the alternative and why it is simpler to run.

**Follow-ups the interviewer will ask.**
- *Why a full snapshot payload with the entity id as key?* The topic is compacted, so after compaction a replaying consumer cannot apply a delta to state it never saw. The key keeps one entity's changes on one partition in order.
- *What does a tombstone do?* A null-value record is how a compacted topic forgets a key. It is kept for the delete retention time and then removed, so a consumer that starts later sees neither.
- *What breaks the router silently?* Renaming outbox columns the router config names. The migration carries a comment saying so.

**Tie to your code.** [L] [`streampulse/docker/debezium/outbox-connector.json`](../../../../../streampulse/docker/debezium/outbox-connector.json), [`ADR-0016`](../../../../../streampulse/docs/adr/0016-debezium-outbox-router-raw-avro.md) (what breaks, observed evidence), [`OutboxCdcIT.java`](../../../../../streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java), [`ADR-0015`](../../../../../streampulse/docs/adr/0015-jpa-flyway-transactional-outbox.md) (gaps). Polling relay for contrast: [`offline-sync-app/internal/outbox/relay.go`](../../../../../GolangExercise/offline-sync-app/internal/outbox/relay.go).

---

## Scenario 6 🔴 Consumer lag is climbing on the aggregate topic: is it an outage or a poison record?

**Situation.** Wednesday 11:15 (example). Lag on the aggregate topic for the sink consumer group climbs for 20 minutes (example: from near zero to tens of thousands). Rows in the metrics table are stale. Logs show repeated redelivery with growing backoff. Someone suggests "dead-letter after 5 failures and move on".

**Level.** 🔴 Senior.

**What's being tested.** Lag diagnosis by partition and queue depth, backpressure as a signal, and why a never-give-up consumer must tell a poison record from a store outage.

**Clarifying questions to ask first.**
1. Which topic's lag is it: raw (the stream processor is behind) or aggregate (the sink is behind)?
2. One partition or all partitions?
3. What is the batch writer's queue depth and the database flush latency?
4. Are there decode failures, or is the whole batch failing?
5. How many partitions does the topic have, and how many consumer threads?

**Flow of control and data.**

```
agg topic ─▶ batch listener ─▶ decode ─(garbage)─▶ dead-letter topic (original bytes + key + reason header) and ack past it
                 └─▶ submit to bounded batch writer ─▶ Postgres upsert ─▶ ack offset AFTER the durable write
store slow: buffer full ─▶ submit fails after 1 s ─▶ no ack ─▶ redelivery, backoff 1 s to 30 s, never gives up ─▶ lag rises (the signal)
batch fails ─▶ retry ─▶ write one by one: some succeed = store up, failures are poison ─▶ dead-letter · none succeed = outage ─▶ fail all
```

**Diagnosis steps.**
1. Identify the topic. Aggregate-topic lag means the sink is behind.
2. Look per partition. One lagging partition is a hot key and more consumers will not help; all partitions lagging means a slow consumer or store.
3. Read the batch writer's queue depth gauge. Near the 2,000 capacity means Postgres is slow. Near empty with growing lag means starved or rebalancing consumers.
4. Check flush latency, error logs and the dead-letter counter. Repeated "refusing to skip" lines mean the recoverer refuses to drop records by design.
5. Check the ceiling: 6 partitions and 3 threads means at most 2 times headroom (from config), and consumers beyond the partition count do nothing.

**Fix now vs fix properly.**
- Now: fix the slow dependency (the database). Do not dead-letter healthy records. Scale consumer threads only up to the partition count.
- Properly: alert on lag growing or above a small constant, not on lag above zero (I observed lag of 1 per partition on an idle, caught-up group, which I believe is the transaction commit marker of the exactly-once producer, but did not confirm). Autoscaling on lag is not built. Decode-level validation rejects the common deterministic poison causes first. A record that is poison but alone in its batch cannot be told from an outage by the isolation rule (ADR-0013).

**How you'd test it.** A poison-record integration test interleaves 2 garbage records between healthy ones (5 good, 2 garbage, 5 good) and asserts 10 stored rows, committed offsets totalling 12, exactly two dead letters with their keys and a decode reason header, and the counter at 2. A fault-injection test throws after the durable write and before the ack three times, and asserts 60 rows, correct values, offsets of 60 and an empty dead-letter topic. Both inject exceptions, not process kills.

**Spoken answer (60-90 seconds).**
I would not dead-letter after N attempts, because during a database outage that turns healthy records into data loss. So the first question is poison or outage. In my sink, undecodable records go to a dead-letter topic with their original bytes, key and a reason header, and the listener acknowledges past them. When a batch keeps failing, the writer retries and then writes the records one at a time: if some succeed, the store is up and the failures are poison; if none succeed, it cannot tell, so it treats it as an outage and fails everything, retrying with exponential backoff from one second to thirty with no attempt limit. For lag I go in order: which topic, one partition or all, and the writer's queue depth. The consumer group has six partitions and three threads, so I have exactly two times headroom and then a wall. What I did not measure is peak lag or drain time under load, and I have not built autoscaling on lag.

**Follow-ups the interviewer will ask.**
- *Why acknowledge only after the durable write?* Then lag means "work not yet stored", which is the honest meaning, and a crash redelivers, which the upsert makes harmless.
- *Why is `max.poll.interval.ms` 300,000?* It must exceed the poll budget (30 s) plus the longest backoff (30 s) plus the worst flush retry, or the broker evicts the consumer in the middle of an outage. A wiring test asserts the inequality.
- *Why not a distributed transaction across Postgres and Kafka offsets?* The database is not a Kafka resource. The primary key and a `computed_at` guard in the upsert make a replay a no-op (ADR-0013).

**Tie to your code.** [L] [`SinkConfig.java`](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/config/SinkConfig.java) (never-give-up error handler), [`BatchWriter.java`](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java) (isolate), [`sink-writer application.yml`](../../../../../streampulse/services/sink-writer/src/main/resources/application.yml), [`PoisonRecordIT.java`](../../../../../streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/PoisonRecordIT.java), [`NoLossNoDoubleCountIT.java`](../../../../../streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/NoLossNoDoubleCountIT.java), [`ADR-0013`](../../../../../streampulse/docs/adr/0013-sink-durable-then-commit.md), lag playbook in [`docs/deep-dive.md`](../../../../../streampulse/docs/deep-dive.md).

---

## What not to claim in these scenarios

- Do not say any pipeline is exactly-once. Say at-least-once delivery plus idempotent processing.
- The original FieldSync consumer retries forever and does not dead-letter. Dead-lettering exists in the webhook worker and the two-way loader.
- The ticket-booking projector logs and marks bad events processed. It does not dead-letter.
- The Redis claim is not crash-safe between claim and publish. That is my reading, untested.
- No alert on replication-slot lag, no outbox retention job, no autoscaling on lag, no replay tooling for dead letters.
- Relay throughput and latency figures are derived from constants, and peak lag and drain time were not measured.
- The crash tests inject exceptions, not process kills, and do not cover a broker or Postgres failing mid-write.
- Debezium and Kafka behaviours were observed on one image tag. Verify against current docs, as well as the Postgres replication-slot view and any WAL retention setting I mention.
