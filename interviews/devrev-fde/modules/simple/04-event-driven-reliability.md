# Module 04 in plain English: Event-driven reliability

> **Read this first**
> - **What it is for:** learning how to build pipelines that stay correct when messages are retried, repeated or crash halfway.
> - **Who it is for:** a beginner. Every term is explained the first time it appears.
> - **Full version:** [04-event-driven-reliability.md](../04-event-driven-reliability.md) (the senior module with code and exact numbers).

Lanes used in this file:
- **[P]** shipped at Couchbase. Nothing in this module is **[P]**.
- **[L]** my own code. Every phase here is **[L]**.
- **[K]** knowledge only. Where I only read about a thing, I say so.

The code is in three projects, all siblings of the `AI` repo under `/Users/aashishkumar/Documents/GitHub/`:
- `GolangExercise/offline-sync-app` ([folder](../../../../../GolangExercise/offline-sync-app/)): "FieldSync", Go, Postgres, EventBridge and SQS.
- `GolangExercise/ticket-booking` ([folder](../../../../../GolangExercise/ticket-booking/)): Go, an outbox, a Redis projector and a payment saga.
- `streampulse` ([folder](../../../../../streampulse/)): Java 21, Spring, Kafka, Debezium. Design decisions are in its [ADR folder](../../../../../streampulse/docs/adr/) (ADR means architecture decision record, a short note explaining a choice).

I did not run any of these tests while writing the module. Every "the test asserts" line comes from reading the test source. Run them yourself before an interview. Numbers are labelled by origin: config, observed once in a recorded run, derived by arithmetic, or not measured.

---

## Phase 1 — Why events, and delivery semantics

**Analogy: a post office.** You drop a letter in the box and walk away. You do not wait at the recipient's door. The post office may deliver a letter twice by accident, but it should never lose one. The recipient must cope with a repeat.

### Beginner points

**Why use events instead of calling every downstream system directly?**
- An event is a small message saying "something happened".
- In FieldSync, the write path never calls a downstream system.
- It commits the record and an event row in one transaction (a group of database changes that all succeed or all fail). Consumers pick the event up later.
- A slow or broken consumer cannot fail the user's write.
- I can add a new consumer without touching the writer.
- StreamPulse's control plane makes the same choice. ADR-0015 records that request latency and availability do not depend on Kafka.
- The price: consumers see a change a little later, and sometimes see it twice.

**What does at-least-once delivery mean, and what must the consumer do?**
- The system keeps retrying until it knows the message was handled. A message may arrive more than once. It is not silently dropped.
- In my relay (the program that moves events from the database to a bus), publish happens first and the row is marked published afterwards.
- A crash in between sends the same event again on the next tick.
- So the consumer must make a repeat harmless.
- In FieldSync that is a `processed_events` table keyed by event id and consumer name.
- In StreamPulse it is an upsert (insert or update) keyed by the aggregate's identity.

### Intermediate points

**Where exactly can a duplicate enter my outbox relay?**
- The relay lists unpublished rows, calls `PutEvents` for one row, and only then marks it published.
- `PutEvents` is the EventBridge call that sends an event.
- If the process dies after EventBridge accepted the entry but before `MarkEventPublished` commits, the row is still unpublished. The next tick publishes it again.
- I also check `FailedEntryCount`. EventBridge can return success for the call while rejecting an entry inside it.
- A rejected or failed entry stays unpublished and is retried. So the guarantee is at-least-once by construction.
- The order of the two calls is the whole guarantee. Publish then mark gives duplicates. Mark then publish would give loss.

### Senior points

**Can I promise exactly-once?**
- No. I promise at-least-once delivery plus idempotent processing (doing it twice has the same effect as once). That gives an effectively-once result in the stores.
- Kafka Streams in my stream processor runs with `processing.guarantee: exactly_once_v2`. The config comment says that covers Kafka to Kafka only.
- ADR-0012 says anything that reads the topic and writes elsewhere still sees at-least-once.
- The sink writer therefore stores each aggregate with an upsert. The key is tenant, title, region, metric and window start.
- It acknowledges the offset (its "I have handled this" marker) only after the durable write. That is ADR-0013.
- The evidence is `NoLossNoDoubleCountIT`:
  - three injected failures between the write and the acknowledgement,
  - 60 aggregates produced (5 titles, 6 windows, 2 regions, from the test constants),
  - the test asserts 60 rows, correct values, committed offsets of 60 and an empty dead-letter topic.
- The boundary: the injected failure is an exception, not a killed JVM. The Redis live projection can still show a record twice after a redelivery.

**Why not wrap the Postgres write and the Kafka offset commit in one transaction?**
- The database is not a Kafka resource, so Kafka transactions cannot include it.
- ADR-0013 rejects a distributed transaction as machinery this write does not need.
- Instead I put correctness in the write itself.
  - The primary key makes a replay land on the same row.
  - A `computed_at <=` guard makes a replay a no-op, and stops an older computation from overwriting a newer one.
- The cost: I must keep that upsert idempotent forever. A test exercises it through real redelivery.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Event | A small message saying something happened. |
| At-least-once | Retried until handled; may arrive more than once; never silently lost. |
| Exactly-once | Each message handled once; hard to promise across systems. |
| Effectively-once | At-least-once delivery plus idempotent handling. |
| Relay | The program that moves outbox rows to the bus. |
| Offset | A consumer's position marker in a Kafka partition. |
| Upsert | Insert a row, or update it if it exists. |
| ADR | A short written record of a design decision. |

**Say it in one breath:** I promise at-least-once delivery plus idempotent processing, never exactly-once, and I put the safety in the write so repeats are harmless.

---

## Phase 2 — Idempotency

**Analogy: a restaurant order slip.** If the waiter carries the same numbered slip twice, the kitchen sees the number and cooks it once. The number must be written by the customer's side, so a lost reply does not look like a new order.

### Beginner points

**What is idempotency, and why should the client generate the id?**
- Idempotency means doing the same operation twice has the same effect as doing it once.
- In StreamPulse, `EventId` is a UUID (a random unique id) created by the client. The ingest path must use the id the client sent.
- If the server made the id, a retry after a lost response would look like a brand new event. The duplicate could not be detected.
- A client can make a UUID offline with no round trip. That matters for players that buffer telemetry and flush later.
- It is the same reasoning as a payment provider's `Idempotency-Key` header.

### Intermediate points

**How do I claim an event id atomically in Redis, and what if Redis is down?**
- I use `setIfAbsent` with a TTL (time to live). It maps to Redis `SET key value NX EX`.
- The test and the set happen in one server-side step, so exactly one caller wins.
- The key is namespaced by tenant through `EventId.idempotencyKey`. One tenant's ids can never suppress another's. That would be silent cross-tenant data loss.
- The TTL is 24 hours, from the ingest config. It defines the deduplication window. A retry after that window is treated as new.
- `setIfAbsent` returns a boxed Boolean that can be null. Treating null as "already seen" would silently drop events. So null counts as claimed.
- If Redis is unreachable, the store returns `unavailable`. The use case fails open: it publishes without deduplication and counts it.
- ADR-0007 judges a duplicate recoverable and a lost event not.

**What does a dedupe table look like, and why must the claim share a transaction with the effect?**
- FieldSync has `processed_events`, with a primary key of event id and consumer name.
- The webhook receiver has `webhook_inbox`, with a primary key of the delivery id.
- Both use `INSERT ... ON CONFLICT DO NOTHING`.
- The inbox query returns the affected row count. One statement says both "stored" and "first time". One row means first delivery. Zero rows means duplicate.
- The claim must commit together with the side effect. Otherwise a crash between them either loses the effect or repeats it.
- Honest limit: my original `consume.RunOnce` marks the event processed in a separate statement after the handler returns. A crash in that gap repeats the handler. So the handlers must be idempotent on their own.
- I ran a sketch of the claim-plus-effect-in-one-transaction pattern in a scratch module with a fake transaction. A crash before commit, then two redeliveries, gave exactly one applied effect.
- It only works when the effect and the claim live in the same database. That is the boundary of the pattern.

### Senior points

**The Redis claim happens before the publish. What breaks?**
- The claim is a reservation, not a record of completion.
- A claim without a publish turns the client's retry into a silent loss.
- The caught failure: if the publish throws, `IngestService` releases the claims before rethrowing. `release` is best-effort and never throws, so the caller sees the real publish error.
- A test named `withoutTheReleaseTheRetryIsSwallowed` keeps that bug executable, so nobody deletes the release as dead code.
- The circuit breaker makes the bug worse. It fails fast for its whole open window (30 seconds), so every batch in that time would be swallowed.
- The failure I have not closed: a process crash between the claim and the publish. The release only runs inside the catch.
  - Then the client's retry is answered as a duplicate for up to 24 hours (from config), and the events are gone.
  - That is my reading of the code. I have not tested it.
  - A pending/done claim state, or downstream deduplication, would be the fix.

**Why fail open on a Redis outage, and when fail closed?**
- For telemetry the loss is asymmetric. A duplicate inflates a metric, and is visible through a counter and a `degraded: true` response. A gap is permanent, because the player has moved on.
- Producer idempotence (`enable.idempotence: true` in the gateway config) still prevents duplicates from Kafka-level retries. Only genuine client resubmissions get through.
- For payments or orders I would fail closed every time. ADR-0007 says so.
- The flag `fail-open-on-idempotency-error` puts that decision in configuration, not in a catch block.
- The same idea appears in the ticket-booking saga (a multi-step flow with undo steps). The charge key is a SHA-256 hash over user, order and hold. It is stable across retries of one checkout and different for a new order.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Idempotency key | A client-made id that lets the server spot a repeat. |
| Dedupe table | A table of ids already handled. |
| TTL | How long a record lives before it expires. |
| Fail open | When a check is down, let the request through. |
| Fail closed | When a check is down, refuse the request. |
| Compensating action | An undo step that gives back a reservation. |
| Circuit breaker | A switch that stops calling something that keeps failing. |
| Saga | A multi-step flow with undo steps instead of one big transaction. |

**Say it in one breath:** The client makes the id, the server claims it atomically, and for telemetry I fail open because a duplicate is recoverable and a lost event is not.

---

## Phase 3 — The transactional outbox

**Analogy: writing the letter and the mailing slip on the same page.** If you tear the page, both go together. You never mail something with no record, and you never keep a record of something never written.

### Beginner points

**What is the dual-write problem?**
- It is when one operation must update two systems, here a database and a message bus, and nothing makes the two updates atomic (all or nothing).
- If I save the order and then publish the event, a crash or broker error between them leaves the database changed and the event never sent.
- If I publish first and the save fails, I announce something that never happened.
- Retrying cannot fix a process that has died. The application alone cannot make the pair atomic.
- I ran a small sketch against fakes. With a bus that fails once, the dual write had already saved the order when the publish failed. The outbox version saved the order and the event row in a single call.

### Intermediate points

**How does my Go code implement the outbox, and where is the transaction boundary?**
- `TxRunner.Sync` begins one transaction and runs the idempotent upserts through a Querier (a database handle) bound to that transaction.
- For every record whose outcome was `applied`, it inserts a `domain_events` row with `events.Publish` before committing.
- A record that was ignored as stale, conflicted, or blocked by the photo cap produces no event. Events describe state changes, not rejected writes.
- A separate relay later scans `published_at IS NULL` and sends the rows to EventBridge.
- The key discipline: `Publish` must receive the transaction-bound Querier. The ticket-booking version says so in capitals in its comment.
- Rolling the whole batch back on an infrastructure error is safe only because every upsert is idempotent. The client's own retry replays the identical batch.

### Senior points

**What does the outbox guarantee, and what does it not?**
- It guarantees a change and its announcement exist together or not at all.
- It guarantees nothing about delivery count or delivery order.
- In StreamPulse the outbox port uses `Propagation.MANDATORY`. Calling it with no transaction throws, instead of opening one that would commit on its own.
- `REQUIRES_NEW` would let the row outlive a rolled-back change. ADR-0015 records that mutating it to `REQUIRES_NEW` turns two of the atomicity tests red.
- How I tested it in the Java version:
  - `OutboxAtomicityIT` rolls back after the announcement was written. It asserts zero tenants and zero outbox rows.
  - It first asserts the row is visible inside the transaction, so the test is not vacuous (not trivially passing).
  - A second test adds a CHECK constraint that makes the outbox insert fail, and asserts the business change rolled back too.
- The gaps are real:
  - No retention job exists for the outbox table.
  - Nothing alerts on relay lag. Both come from ADR-0015.
  - My FieldSync integration test checks event counts for applied and stale writes. It does not force a mid-transaction failure.

**What are the throughput and latency limits of my polling relay?**
- There are two configurations.
- Local-dev loop: ticks every 5 seconds, takes 25 rows per tick, and calls `PutEvents` once per row. By arithmetic that is at most about 5 events per second, with up to roughly 5 seconds of added latency.
- Terraform schedule for the AWS entrypoint: `rate(1 minute)` with one `RunOnce` per invocation. The ceiling is 25 events per minute, about 0.4 per second, with up to a minute of latency.
- Both figures are derived from constants I read. They are not measured. I did not verify the Terraform was applied.
- That is acceptable for a field-survey app. The migration comment says no CDC is needed at this scale.
- If volume grew I would: loop inside an invocation until the backlog drains, use the multi-entry `PutEvents` call, or move to Debezium as I did in StreamPulse.
- I would also fix the ordering column. My FieldSync relay orders by `occurred_at`. Ticket-booking added a `BIGSERIAL outbox_seq` after a real bug (see Phase 6).

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Dual write | Updating a database and a bus with no shared atomicity. |
| Outbox | A table where events are written in the same transaction as the change. |
| Atomic | All of it happens, or none of it. |
| Transaction | A group of database changes that succeed or fail together. |
| Polling relay | A loop that checks the outbox every few seconds and sends new rows. |
| Vacuous test | A test that passes without really checking anything. |
| Retention job | A cleanup job that deletes old rows. |

**Say it in one breath:** The outbox writes the change and its event in one transaction so they exist together, and my polling relay is slow but fine at this small scale.

---

## Phase 4 — Change data capture with Debezium

**Analogy: a court stenographer.** The stenographer writes down every spoken statement from the record without anyone needing to report it. The application just speaks (writes to its own database). Debezium copies each statement out.

### Beginner points

**What is change data capture (CDC), and why use it for an outbox?**
- CDC reads the database's write-ahead log (the log of every committed change) and turns row changes into events. The application needs no polling loop.
- In StreamPulse, the Debezium Postgres connector reads the `control_plane.outbox` table through a replication slot (a bookmark in the log). It publishes to the `config.changes.v1` Kafka topic.
- The application only inserts a row in its own transaction. Debezium does the publishing.
- ADR-0016 records the alternative I did not build: a polling publisher inside the service. It is simpler to run but adds polling latency.

### Intermediate points

**What is in the connector configuration?**
- The outbox router takes the Kafka key from `aggregate_id`.
- It takes the value from the `payload` column.
- It routes every row to the single topic `config.changes.v1`, whatever the `aggregate_type`.
- The payload column is `bytea` (raw bytes) holding raw Avro. So the value converter is the byte-array converter, and the key converter is the string converter.
- A NULL payload becomes a null-value record, because `route.tombstone.on.empty.payload` is true. That is how a delete reaches a compacted topic.
- A tombstone is a record with a key and a null value, meaning "forget this key".
- The additional placement setting copies the `operation` column into a header named `operation`. It copies `aggregate_type` into a header named `entityKind`.
- The connector file is the same one the compose stack registers and the integration test uses. So the test and the stack cannot drift.
- The coupling to name: the column names in the outbox migration are the router's configuration. Renaming `payload` or `aggregate_id` breaks the connector silently. The migration carries a comment saying so.

**How do I prove the CDC path end to end?**
- `OutboxCdcIT` starts Postgres with `wal_level=logical`, plus Kafka and Debezium Connect in Testcontainers (real services in throwaway containers).
- It registers the real connector file, then creates, updates and deletes one tenant.
- It reads the topic from the beginning and asserts three records on one key, in one partition, with increasing offsets.
- The first two decode as Avro `ConfigChange` records with operations CREATED and UPDATED. The third has a null value.
- It also asserts each record's `changeId` equals its outbox row id. A consumer uses that to deduplicate a replay.

### Senior points

**What are the failure modes of the Debezium relay, and what did I observe?**
- One: the connector is down. The control plane kept accepting changes (ADR-0016 records 201 and 200 responses while Connect was stopped). Outbox rows accumulated. Postgres retained write-ahead log for the inactive slot.
  - An abandoned slot would eventually fill the disk. A retired connector needs `pg_drop_replication_slot`.
  - I have no alert on slot lag.
- Two: at-least-once delivery after a connector restart. Consumers use `changeId` and `version` to ignore duplicates.
- Three: ordering holds per key only. A consumer must not assume a tenant's record precedes its title's.
- Four: compaction. A tombstone is kept for `delete.retention.ms` and then removed. A consumer that starts later sees neither the key nor its deletion.
- The one run I recorded gave three records at offsets 0, 1 and 2, with Avro payloads of 210 and 214 bytes (observed once, ADR-0016).
- I did not benchmark throughput or end-to-end latency.
- These behaviours were observed on image `3.0.8.Final`. Verify against current Debezium docs when upgrading.

**Why is the payload a full snapshot and the key the entity id?**
- The topic is compacted (Kafka keeps only the last record per key). After compaction the intermediate records are gone.
- A consumer replaying from the start would apply a delta to a state it never saw.
- A full snapshot per key makes the last record per key enough to rebuild a cache.
- The key is the entity id, so all changes to one entity land on one partition in order. That is the only ordering Kafka gives.
- The cost: I cannot reconstruct history from this topic. The outbox table in Postgres remains the audit trail.
- The topic's contract file (AsyncAPI) says this: the payload must be a full snapshot, never a delta, and a delete is a null-payload tombstone.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| CDC | Copying row changes out of a database's log as events. |
| Debezium | A tool that does CDC into Kafka. |
| Write-ahead log | The database's record of every committed change. |
| Replication slot | A bookmark that keeps the log until a reader has read it. |
| Tombstone | A record with a null value meaning "delete this key". |
| Compacted topic | A topic that keeps only the last record per key. |
| Avro | A compact binary format for structured messages. |
| Testcontainers | A library that starts real services in throwaway containers for tests. |

**Say it in one breath:** Debezium copies outbox rows from the database log to a compacted Kafka topic keyed by entity id, with full snapshots and null-value tombstones for deletes.

---

## Phase 5 — Consumers, retries, poison messages and dead letters

**Analogy: a mail sorter with a "problem" bin.** If an envelope is unreadable, the sorter does not keep staring at it and block the belt. It puts it in the problem bin with a note, and carries on. But if the whole building lost power, the sorter does not throw every letter in the bin.

### Beginner points

**What happens in my original FieldSync consumer when the handler fails?**
- The failed event is simply not marked processed. The next tick selects it again and retries it. The rest of the batch continues.
- That is at-least-once, and safe for a transient error such as a database blip.
- The honest weakness: the loop has no attempt counter and no dead-letter path. A permanently bad event is retried forever.
- Dead-lettering exists in later code (the two-way sync package), not in this original consumer.

**What is a poison message, and what is a dead-letter queue?**
- A poison message can never be processed successfully. For example, a body that is not valid JSON. Retrying it only burns capacity and blocks work behind it.
- A dead-letter queue or table is where I park such a message, with its raw bytes, the reason and the attempt count.
- The main flow keeps moving, and a human can inspect it later.
- In Kafka the poison record sits in front of the offset. Without a dead letter, one bad record stops its whole partition.

### Intermediate points

**How does my webhook worker cap retries and dead-letter?**
- Each failure runs in its own transaction. It increments `attempts` and stores `last_error`.
- When attempts reach the configured maximum, it inserts a row into `sync_dead_letters` with the raw body, the reason and the attempt count. Then it marks the inbox row dead so it is no longer selected.
- The raw body is stored as bytes, because a poison body may not be valid JSON.
- The integration test sends a validly signed body of `not json`. It asserts exactly 3 attempts, a reason and the raw body. It also asserts attempts stop growing afterwards.
- The loader makes the same decision for pushes:
  - exhausted retries dead-letter,
  - permanent 4xx responses dead-letter,
  - anything else (such as a cancelled context) is returned so the event stays unprocessed.
- What is not solved: the docs list no backoff between inbox retries, so a poison body burns the same attempts as a transient error. There is no replay tooling and no alert on dead-letter growth.

### Senior points

**How does the Kafka sink tell a poison record from a store outage, and why never dead-letter after N attempts?**
- A poison record and an outage need opposite handling. The sink separates them.
- Records that cannot be decoded go to the dead-letter topic with the original bytes, the original key and a `dlt-reason` header. The listener still acknowledges past them.
- When a batch keeps failing, the batch writer retries it. Then it writes the records one at a time.
  - If some succeed, the store is up and the failures are poison.
  - If none succeed, it cannot tell. It treats the failure as an outage and fails every record.
- An outage is retried with exponential backoff, 1 second doubling to 30 seconds (from config). There is no attempt or elapsed-time limit.
- The recoverer deliberately throws "refusing to skip". Dead-lettering healthy records during an outage would turn it into data loss.
- `PoisonRecordIT` sends 5 good records, 2 garbage records and 5 more good ones. It asserts:
  - 10 stored rows,
  - committed offsets totalling 12,
  - exactly two dead letters, keyed `poison-1` and `poison-2`,
  - a counter of 2.
- The boundary, stated in ADR-0013: a poison record alone in its batch cannot be told from an outage by the isolation rule. So the decoder rejects the common deterministic causes first.
- The test ran on a single-broker Testcontainers setup.

**Where in my own code is a bad message dropped without a dead letter?**
- In the ticket-booking projector. An unrecognised event type, a malformed payload or an unknown seat ordinal is logged and then marked processed.
- The event is skipped for good, with only a log line as evidence.
- I chose that so one bad row cannot stall the read model. But it is a silent drop. I would add a dead-letter table and a counter before calling it production-ready.
- The same file shows the opposite choice for a Redis failure. The event is left unprocessed so it retries. Marking it processed would leave a permanent hole in the bitset.
- On AWS, the Terraform defines an SQS dead-letter queue per consumer with `maxReceiveCount = 5` and 14-day retention.
- The Lambda event source mapping uses `ReportBatchItemFailures`, so only failed messages are redelivered.
- That is configuration I read. I did not verify it was applied to an account.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Poison message | A message that can never be processed successfully. |
| Dead-letter queue (DLQ) | A parking place for messages that could not be handled. |
| Backoff | Waiting longer between each retry. |
| Outage | The store is down; healthy records fail too. |
| Isolation | Retrying records one at a time to find which is bad. |
| Acknowledge (ack) | Telling the broker "I have handled this offset". |
| `maxReceiveCount` | How many times SQS delivers before sending to the DLQ. |

**Say it in one breath:** Retry what can heal, dead-letter what cannot, and never confuse an outage with a bad record, because dead-lettering during an outage turns it into data loss.

---

## Phase 6 — Ordering, partitions and consumer lag

**Analogy: checkout lanes in a supermarket.** People in one lane are served in order. Between lanes there is no order. Putting all of one family in the same lane keeps their items in sequence. Too few lanes, and a queue builds up.

### Beginner points

**Does Kafka keep messages in order?**
- Only within a single partition (one ordered lane of a topic).
- Messages with the same key go to the same partition, so they stay in order for that key.
- There is no ordering across different keys.
- In StreamPulse the raw telemetry topic is keyed by `sessionId`. One viewing session's events stay in order. Ordering between two sessions is not promised.

**What is consumer lag?**
- It is how far a consumer group's committed offset is behind the end of the log, per partition.
- In my sink the offset is acknowledged only after the durable write. So lag means work not yet stored. That is the meaning I want.
- I read it per partition. One lagging partition points to a hot key. All partitions lagging points to a slow consumer or store.

### Intermediate points

**How did I choose partition keys, and what does it cost?**
- I wrote the choice and the rejected alternatives into the AsyncAPI contract.
- Raw telemetry is keyed by `sessionId`.
  - `tenantId` would give three hot partitions with only three tenants, and the rest idle.
  - A null key would give perfect balance and no ordering at all.
- The cost I accept: aggregating per title needs a repartition (a network hop and an extra topic). Ordering is a correctness property. Repartitioning is a performance cost.
- The topic has 12 partitions. That caps consumer parallelism and divides evenly by 1, 2, 3, 4, 6 and 12.
- Raising the count later rehashes keys and breaks ordering. So pick above current need.

**Where does ordering matter in my Go projects, and how is it enforced?**
- In ticket-booking, the projector applies seat transitions to a Redis bitset (a compact row of on/off flags).
- Applying two same-direction transitions out of their real order silently no-ops the second one, through its own idempotency check.
- A test that applied 220 real transitions produced only 112 applied changes. That exposed that `created_at` is not a strict total order.
- So I added a `BIGSERIAL outbox_seq` and ordered by it. The migration comment records those numbers.
- The relay does not care about delivery order. The projector does.
- In FieldSync I avoid depending on delivery order at the data layer. An atomic version gate in SQL applies an incoming external version only if it is strictly newer.
- One gap remains: my FieldSync relay and consumer queries still order by `occurred_at`.

### Senior points

**The aggregate-topic lag is climbing. How do I diagnose it?**
- Three questions in order.
  - Which topic's lag is it? Raw-topic lag means the stream processor is behind. Aggregate-topic lag means the sink is behind.
  - One partition or all? One partition is a hot key, and more consumers will not help.
  - What is the batch writer's queue depth? Near its 2,000 capacity means Postgres is slow. Near empty with growing lag means consumers are starved or rebalancing.
- The ceilings come from partitions. The aggregate topic has 6 partitions and the sink runs 3 threads (both from config and the AsyncAPI file). That is exactly 2x headroom and then a wall.
- Backpressure (a full buffer pushing back) is the signal by design.
  - A full buffer fails `submit` after 1 second.
  - The listener throws without acknowledging.
  - Redelivery backs off from 1 to 30 seconds, and lag rises.
- `max.poll.interval.ms` is 300,000. It is deliberately above the 30-second poll budget plus the 30-second maximum backoff. A wiring test asserts that inequality.
- What I observed: lag of 1 on each of the 6 partitions with the sink idle after a 90-second run.
  - I believe that is the transaction commit marker of the exactly-once producer. I did not confirm it by dumping the log.
- I did not measure peak lag or drain time under load. Autoscaling on lag is not built.

**If the sink consumes in parallel and in batches, how is it correct without ordering?**
- It does not rely on arrival order. It relies on a guard in the write.
- The upsert only replaces a row whose stored `computed_at` is older than or equal to the incoming one. Reordering and replays cannot move a value backwards.
- The key is the aggregate's identity, so a redelivery overwrites itself.
- I would not use the same trick where every intermediate state matters, such as a ledger. That needs per-key ordering and a single writer per key.
- An alert on "lag greater than 0" would fire forever on this topic, given the observed lag of 1. The alert should look at lag growing, or above a small constant.
- The repo's observability notes describe the alert that way. I have not verified that rule file or run its tests.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Partition | One ordered lane of a Kafka topic. |
| Partition key | The value that decides which partition a message goes to. |
| Consumer group | Consumers that share the work of a topic. |
| Consumer lag | How far behind the end of the log a consumer is. |
| Hot key | One key getting far more traffic than others. |
| Backpressure | A full buffer slowing down the producer or reader. |
| Repartition | Moving data to a new key, with a network hop. |
| Rebalance | Kafka reassigning partitions among consumers. |

**Say it in one breath:** Kafka orders only within a partition, so I key by what correctness needs, and I read lag as work not yet stored, per partition.

---

## Phase 7 — Testing reliability

**Analogy: a fire drill.** You do not prove the exits work by reading the map. You trigger the alarm at the exact point you worry about and watch what happens. A drill with a fake alarm still does not prove a real fire.

### Beginner points

**Why test with a real database or broker, not only mocks?**
- Reliability lives in the interaction: transaction boundaries, unique constraints and offset commits. A mock cannot reproduce them.
- In FieldSync, the relay's control flow is unit-tested against a hand-written fake publisher.
- The atomic SQL and the transaction are tested against real Postgres under the `integration` build tag.
- In StreamPulse, the integration tests start real Kafka, Postgres, Redis and Debezium in Testcontainers.
- I keep both layers. Unit tests are fast. Integration tests prove the failure paths.

### Intermediate points

**How do I unit test the relay's failure behaviour?**
- I give the relay a fake publisher that can return an error or a rejected entry.
- I give it a mocked Querier from gomock, with no expectation for `MarkEventPublished` on the failure path. gomock fails the test if the relay marks a failed event published.
- The technique: absence of an expected call is the assertion.
- Other tests assert that a failed first entry does not stop the second, and that a rejected entry inside a successful call is not marked either.
- The same tests are the evidence for the at-least-once claim in Phase 1.

### Senior points

**How do I test a crash, and what does it not prove?**
- I inject the crash at the exact point I worry about.
- In FieldSync, a transactor wrapper runs the page's work and then returns "simulated crash after apply, before commit" on the second call. The test asserts:
  - only page 1 is applied,
  - the checkpoint points at page 2's cursor,
  - the resumed run fetches from that cursor and ends with 7 links, 7 events and zero work items with more than one event.
- In StreamPulse, a test-only `PreAckHook` throws after the durable write and before the acknowledgement, three times. The test asserts:
  - 60 rows with unchanged values,
  - committed offsets of 60,
  - more write attempts than records (so redelivery really happened),
  - an empty dead-letter topic.
- Neither test kills a process. Both inject an exception.
- ADR-0013 and the test's own javadoc say a broker or Postgres failing mid-write, and a killed JVM, are not covered.
- The idempotent upsert is what makes a real crash safe. I have not demonstrated it with a kill signal.
- The Debezium restart case I observed by hand (ADR-0016). It is not automated.

**How do I test poison records, and how do I know a test can fail?**
- `PoisonRecordIT` puts two garbage records between healthy ones. It asserts three things:
  - healthy rows are stored,
  - the poison bytes arrive on the dead-letter topic untouched, with the key and a `dlt-reason`,
  - the committed offset total includes the poison records, so the group is not blocked.
- To know a test can fail, I mutate the code.
  - The two-way sync doc records a by-hand mutation check. Removing dead-lettering, the checkpoint write or the version gate each turned at least one test red.
  - `IngestServiceTest` records that a single-shot concurrency test passed against a deliberately broken check-then-set store.
  - So the final version loops 200 iterations with 8 threads (constants in the test). It was verified to fail against that broken store.
- Repetition raises the chance of hitting a race. It cannot prove the race is absent.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Integration test | A test using real databases or brokers. |
| Fault injection | Making a failure happen on purpose at one exact point. |
| Mutation check | Break the code on purpose to see if a test notices. |
| Fake | A hand-written stand-in for a real dependency. |
| gomock | A Go tool that makes mock objects and checks calls. |
| Checkpoint | A saved position so work can resume. |
| Race | A bug that depends on the timing of parallel work. |

**Say it in one breath:** I prove failure paths with real databases and brokers and injected crashes, but my crash tests inject exceptions, not process kills.

---

## Mix-ups to avoid

- **Exactly-once is not what I promise.** I promise at-least-once plus idempotent processing. Kafka Streams exactly-once covers Kafka to Kafka only.
- **A claim is not a completion.** The Redis claim reserves an id. A crash before publish can swallow the client's retry.
- **A retry loop is not a dead-letter path.** My original FieldSync consumer retries forever.
- **An outage is not a poison record.** Dead-lettering healthy records during an outage turns it into data loss.
- **Order is per key, not global.** Kafka orders within a partition only.
- **An injected exception is not a killed process.** My crash tests prove less than a real kill would.

---

## What I built vs what I only know

**Built, my own [L]:**
- FieldSync (Go, Postgres, EventBridge, SQS), ticket-booking (Go, outbox, Redis projector, payment saga) and StreamPulse (Java, Kafka, Debezium).
- Say at-least-once plus idempotent processing. Do not say the pipeline is exactly-once.
- The original FieldSync consumer does not dead-letter. It retries forever. Dead-lettering exists in `webhook.Worker` and `twoway.Loader`.
- The ticket-booking projector logs and marks bad events processed. It does not dead-letter.
- The Redis claim is not crash-safe. A crash between the claim and the publish can swallow the client's retry for the 24 hour TTL.
- The outbox table is not maintained. No retention job exists, and nothing alerts on relay or replication-slot lag.
- Throughput, relay latency, peak lag and drain time are not measured. The 5 events per second (local) and 0.4 per second (Terraform schedule) figures are derived from constants.
- Crash tests inject exceptions, not process kills.
- I did not run these tests while writing. Read the test source, then run them yourself before the interview.

**Shipped at Couchbase [P]:**
- Nothing from this module.

**Knowledge only [K]:**
- The SQS dead-letter queue and the AWS relay schedule: the Terraform exists, and I did not verify an applied deployment.
- Debezium and Kafka behaviour beyond what the connector file, the tests and ADR-0016 show, such as tombstone retention and how `tombstones.on.delete` interacts with the router. Say "verify in current docs".
