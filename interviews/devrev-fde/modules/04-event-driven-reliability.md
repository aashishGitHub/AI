# Module 04 — Event-driven reliability

> This module is about making asynchronous pipelines safe to retry: delivery semantics, idempotency, the transactional outbox, Debezium change data capture, consumer failure handling, ordering and lag, and how I test all of it. The code is mine, so every lane is **[L]**: `GolangExercise/offline-sync-app` (FieldSync, Go, Postgres, EventBridge and SQS), `GolangExercise/ticket-booking` (Go, outbox plus a Redis projector and a payment saga), and `streampulse` (Java 21, Spring, Kafka, Debezium). Paths below are relative to `/Users/aashishkumar/Documents/GitHub/`. I did not run any of these tests while writing this guide, so every "the test asserts" statement comes from reading the test source, not from a fresh run. Numbers are labelled by origin: config, observed in an earlier run recorded in the repo, derived by arithmetic, or not measured.

## Phases at a glance

| Phase | Purpose in one sentence | Main code |
|---|---|---|
| 1. Why events, and delivery semantics | Decouple the write from its consumers and say honestly what is promised: at-least-once plus idempotent processing. | `offline-sync-app/internal/outbox/relay.go`, `streampulse/services/stream-processor/src/main/resources/application.yml` |
| 2. Idempotency | Make a repeated request or a redelivered message change nothing, using client ids, dedupe tables and an atomic Redis claim. | `EventId.java`, `RedisIdempotencyStore.java`, `IngestService.java`, `sqlc/queries.sql` |
| 3. The transactional outbox | Remove the dual-write window by writing the event row in the same transaction as the state change. | `internal/sync/transactional.go`, `internal/events/events.go`, `JdbcConfigChangeOutbox.java` |
| 4. Change data capture with Debezium | Let Debezium relay the outbox table to a compacted Kafka topic with a stable key and a tombstone for deletes. | `docker/debezium/outbox-connector.json`, `OutboxCdcIT.java` |
| 5. Consumers, retries, poison messages and dead letters | Retry what can heal, dead-letter what cannot, and never confuse an outage with a bad record. | `internal/consume`, `internal/webhook/worker.go`, `SinkConfig.java`, `BatchWriter.java` |
| 6. Ordering, partitions and consumer lag | Pick keys for the ordering that correctness needs, and read lag as work not yet stored. | `streampulse-topics.yaml`, `ticket-booking/sqlc/queries.sql`, `AdvanceLinkVersion` |
| 7. Testing reliability | Prove the failure paths with real databases and brokers, injected crashes and poison records. | `relay_test.go`, `twoway/integration_test.go`, `NoLossNoDoubleCountIT.java`, `PoisonRecordIT.java` |

## Phase 1 — Why events, and delivery semantics (at-least-once, ordering, effectively-once)

### 🟢 Beginner

**Q:** Why use events at all, instead of the writer calling every downstream system directly?

**A:** In my implementation the write path never calls a downstream system. FieldSync commits the record and an event row in one transaction, and the consumers pick the event up later. A slow or broken consumer therefore cannot fail the user's write, and I can add a new consumer without touching the writer. StreamPulse's control plane makes the same choice, and ADR-0015 records that request latency and availability do not depend on Kafka. The price I pay is that consumers see a change a little later, and sometimes see it twice.

**Q:** What does at-least-once delivery mean, and what must the consumer do about it?

**A:** It means the system keeps retrying until it knows the message was handled, so a message may arrive more than once but is not silently dropped. In my relay the publish happens first and the row is marked published afterwards, so a crash in between sends the same event again on the next tick. The consumer must therefore make a repeat harmless. In FieldSync that is a `processed_events` table keyed by event id and consumer name, and in StreamPulse it is an upsert keyed by the aggregate's identity.

### 🟡 Intermediate

**Q:** Show me exactly where a duplicate can enter your outbox relay.

**A:** The relay lists unpublished rows, calls `PutEvents` for one row, and only then marks that row published. If the process dies after EventBridge accepted the entry but before `MarkEventPublished` commits, the row is still unpublished and the next tick publishes it again. I also check `FailedEntryCount`, because EventBridge can return success for the call while rejecting an entry inside it. A rejected or failed entry simply stays unpublished and is retried, so the delivery guarantee is at-least-once by construction.

**Source:** `GolangExercise/offline-sync-app/internal/outbox/relay.go:92-104`

```go
		if err != nil {
			log.Printf("outbox-relay: publish event %s failed, will retry next tick: %v", evt.ID, err)
			continue
		}
		if out.FailedEntryCount > 0 {
			log.Printf("outbox-relay: event %s rejected by EventBridge, will retry next tick", evt.ID)
			continue
		}

		if err := r.q.MarkEventPublished(ctx, evt.ID); err != nil {
			return published, fmt.Errorf("mark event %s published: %w", evt.ID, err)
		}
		published++
```

When I talk about this snippet I point at the order of the two calls, because that order is the whole guarantee: publish then mark gives duplicates, mark then publish would give loss.

### 🔴 Senior

**Q:** Can you promise exactly-once? What do you actually promise in this system?

**A:** I do not promise exactly-once delivery, I promise at-least-once delivery plus idempotent processing, which gives an effectively-once result in the stores. Kafka Streams runs with `processing.guarantee: exactly_once_v2` in my stream processor, but the config comment itself says that covers Kafka to Kafka only, and ADR-0012 says anything that reads the topic and writes elsewhere still sees at-least-once. The sink writer therefore stores each aggregate with an upsert keyed by tenant, title, region, metric and window start, and acknowledges the offset only after the durable write (ADR-0013). The measured evidence is `NoLossNoDoubleCountIT`: three injected failures between the write and the acknowledgement, 60 aggregates produced (5 titles, 6 windows, 2 regions, from the test constants), and the test asserts 60 rows, correct values, committed offsets of 60 and an empty dead-letter topic. The boundary of that claim is that the injected failure is an exception, not a killed JVM, and the Redis live projection can still show a record twice after a redelivery.

**Source:** `streampulse/services/stream-processor/src/main/resources/application.yml:18-21`

```yaml
        # Output records, the state changelog and the consumed offsets commit in one
        # transaction. Kafka to Kafka only: anything that reads telemetry.agg.v1 and writes
        # elsewhere still sees at-least-once, so that consumer must be idempotent (ADR-0012).
        processing.guarantee: exactly_once_v2
```

**Follow-up they will ask:** Why not wrap the Postgres write and the Kafka offset commit in one transaction?

**A:** Because the database is not a Kafka resource, so Kafka transactions cannot include it, and ADR-0013 rejects a distributed transaction as machinery this write does not need. The alternative I chose moves correctness into the write itself: the primary key makes a replay land on the same row, and the `computed_at <=` guard makes a replay a no-op while still stopping an older computation from overwriting a newer one. The cost is that I must keep that upsert idempotent forever, which is why a test exercises it through real redelivery.

## Phase 2 — Idempotency (client-generated ids, dedupe tables, Redis claim)

### 🟢 Beginner

**Q:** What is idempotency, and why should the client generate the id?

**A:** Idempotency means doing the same operation twice has the same effect as doing it once. In StreamPulse the `EventId` is a UUID created by the client, and the ingest path must use the id the client sent. If the server created the id, a retry after a lost response would look like a brand new event and the duplicate could not be detected. A client can also generate a UUID offline with no round trip, which matters for players that buffer telemetry and flush later. This is the same reasoning as a payment provider's `Idempotency-Key` header.

### 🟡 Intermediate

**Q:** How do you claim an event id atomically in Redis, and what happens when Redis is down?

**A:** I use `setIfAbsent` with a TTL, which maps to Redis `SET key value NX EX`, so the test and the set happen in one server-side step and exactly one caller wins. The key is namespaced by tenant through `EventId.idempotencyKey`, so one tenant's ids can never suppress another's. The TTL is 24 hours from the ingest config, which defines the deduplication window, and a retry after that window is treated as new. If Redis is unreachable the store returns `unavailable` and the use case fails open, publishing without deduplication and counting it, because ADR-0007 judges a duplicate recoverable and a lost event not.

**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/redis/RedisIdempotencyStore.java:71-88`

```java
            for (EventId id : eventIds) {
                // Key is namespaced by tenant, so one tenant's ids can never suppress
                // another's — that would be silent cross-tenant data loss.
                String key = id.idempotencyKey(tenant);

                Boolean isNew = redis.opsForValue().setIfAbsent(key, "1", ttl);

                // setIfAbsent returns a BOXED Boolean and can be null (for example inside a
                // pipeline or transaction, where the result is not yet available). Treating
                // null as false would silently drop events, so we treat it as "claimed" —
                // consistent with failing open.
                if (isNew == null || isNew) {
                    claimed.add(id);
                } else {
                    alreadySeen.add(id);
                }
            }
            return ClaimResult.of(claimed, alreadySeen);
```

I use this snippet to show the null handling: `setIfAbsent` returns a boxed Boolean, and treating null as "already seen" would silently drop events, so null counts as claimed.

**Q:** What does a dedupe table look like on the consumer side, and why does the claim belong in the same transaction as the effect?

**A:** In FieldSync the dedupe table is `processed_events` with a primary key of event id and consumer name, and the webhook receiver uses `webhook_inbox` whose primary key is the delivery id. Both rely on `INSERT ... ON CONFLICT DO NOTHING`, and the inbox query returns the affected row count so one statement says both "stored" and "first time". The claim must commit together with the side effect, otherwise a crash between them either loses the effect or repeats it. I should be honest that my original `consume.RunOnce` marks the event processed in a separate statement after the handler returns, so a crash in that gap repeats the handler, and the handlers must be idempotent on their own.

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:58-60`

```sql
-- name: MarkEventProcessed :exec
INSERT INTO processed_events (event_id, consumer_name) VALUES ($1, $2)
ON CONFLICT (event_id, consumer_name) DO NOTHING;
```

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:201-205`

```sql
-- name: InsertWebhookInbox :execrows
-- 1 row = first delivery, 0 rows = duplicate delivery id.
INSERT INTO webhook_inbox (system, delivery_id, body)
VALUES ($1, $2, $3)
ON CONFLICT (system, delivery_id) DO NOTHING;
```

**Illustrative (not from the repo):**

```go
package main

import (
	"context"
	"errors"
)

type Tx interface {
	ExecRows(ctx context.Context, sql string, args ...any) (int64, error)
	Commit(ctx context.Context) error
	Rollback(ctx context.Context) error
}

const claimSQL = `INSERT INTO processed_events (event_id, consumer_name) VALUES ($1, $2) ON CONFLICT DO NOTHING`

func HandleOnce(ctx context.Context, tx Tx, eventID, consumer string, effect func(Tx) error) (applied bool, err error) {
	defer tx.Rollback(ctx)
	n, err := tx.ExecRows(ctx, claimSQL, eventID, consumer)
	if err != nil {
		return false, err
	}
	if n == 0 {
		return false, nil
	}
	if err := effect(tx); err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, errors.Join(errors.New("commit"), err)
	}
	return true, nil
}
```

I ran this in a scratch module with a fake transaction: a crash before commit, then two redeliveries, produced exactly one applied effect. It only works when the effect and the claim live in the same database, which is the boundary of the pattern.

### 🔴 Senior

**Q:** The Redis claim happens before the publish. What breaks, and how did you handle it?

**A:** The claim is a reservation, not a record of completion, so a claim without a publish turns the client's retry into a silent loss. I handle the caught failure: if the publish throws, `IngestService` releases the claims before rethrowing, and `release` is best-effort and never throws so the caller sees the real publish error. A test named `withoutTheReleaseTheRetryIsSwallowed` keeps that bug executable, so nobody deletes the release as dead code. The failure I have not closed is a process crash between the claim and the publish, because the release only runs inside the catch. Then the client's retry is answered as a duplicate for up to 24 hours (from config) and the events are gone. That last point is my reading of the code, not something I have tested, and a pending/done claim state or downstream deduplication would be the fix.

**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java:171-186`

```java
        try {
            publishAndWait(command, newEvents);
        } catch (RuntimeException e) {
            // COMPENSATING ACTION. These ids were claimed a few lines above but never made it
            // to the broker, so the reservation has to be given back.
            //
            // Without this the client's retry finds every id already claimed, gets a 202 with
            // nothing published, drops its copy, and the events are gone for good -- reported
            // as success. The circuit breaker makes it strictly worse: it fails fast for its
            // entire open window, so EVERY batch in those 30 seconds would be swallowed.
            //
            // release() is best-effort and never throws, so the caller still sees the real
            // publish failure rather than a secondary one from Redis. See IdempotencyStore.
            idempotencyStore.release(command.tenantId(), claim.claimed());
            throw e;
        }
```

**Follow-up they will ask:** Why fail open on a Redis outage, and when would you fail closed?

**A:** I fail open because the loss is asymmetric for telemetry: a duplicate inflates a metric and is visible through a counter and a `degraded: true` response, while a gap is permanent because the player has moved on. Producer idempotence (`enable.idempotence: true` in the gateway config) still prevents duplicates from Kafka-level retries, so only genuine client resubmissions get through. For payments or orders I would fail closed every time, and ADR-0007 says so. The flag `fail-open-on-idempotency-error` exists so that decision lives in configuration and not in a catch block. The same idea appears in the ticket-booking saga, where the charge key is a SHA-256 over user, order and hold, stable across retries of one checkout and different for a new order.

## Phase 3 — The transactional outbox (the dual-write problem)

### 🟢 Beginner

**Q:** What is the dual-write problem?

**A:** It is what happens when one operation must update two systems, here a database and a message bus, and nothing makes the two updates atomic. If I save the order and then publish the event, a crash or a broker error between the two leaves the database changed and the event never sent. If I publish first and the save fails, I announce something that never happened. Retrying cannot fix a process that has died, so the application alone cannot make the pair atomic.

**Illustrative (not from the repo):**

```go
package main

import "context"

type Store interface {
	SaveOrder(ctx context.Context, id string) error
	SaveOrderAndEvent(ctx context.Context, id, eventType string) error
}

type Bus interface {
	Publish(ctx context.Context, eventType, id string) error
}

func PlaceOrderDualWrite(ctx context.Context, s Store, b Bus, id string) error {
	if err := s.SaveOrder(ctx, id); err != nil {
		return err
	}
	return b.Publish(ctx, "order.placed", id)
}

func PlaceOrderOutbox(ctx context.Context, s Store, id string) error {
	return s.SaveOrderAndEvent(ctx, id, "order.placed")
}
```

I ran both functions against fakes: with a bus that fails once, the dual write had already saved the order when the publish failed, while the outbox version saved the order and the event row in a single call.

### 🟡 Intermediate

**Q:** How does your Go code implement the outbox, and where is the transaction boundary?

**A:** `TxRunner.Sync` begins one transaction, runs the idempotent upserts through a Querier bound to that transaction, and for every record whose outcome was `applied` inserts a `domain_events` row with `events.Publish` before committing. A record that was ignored as stale, conflicted, or blocked by the photo cap produces no event, because events describe state changes and not rejected writes. A separate relay later scans `published_at IS NULL` and sends the rows to EventBridge. The important discipline is that `Publish` must receive the transaction-bound Querier, and the ticket-booking version says so in capitals in its comment.

**Source:** `GolangExercise/offline-sync-app/internal/sync/transactional.go:42-64`

```go
	defer tx.Rollback(ctx) // no-op once committed

	q := db.New(tx)
	resp, err := NewService(q).Sync(ctx, actor, req)
	if err != nil {
		return Response{}, err
	}

	for i, result := range resp.Locations {
		if result.Outcome != OutcomeApplied {
			continue
		}
		in := req.Locations[i]
		if err := events.Publish(ctx, q, events.Event{
			AggregateType: "location",
			AggregateID:   in.ID,
			Type:          "location.upserted",
			ActorSub:      actor,
			Payload:       in,
		}); err != nil {
			return Response{}, err
		}
	}
```

When I explain this I stress that rolling the whole batch back on an infrastructure error is safe only because every upsert is idempotent, so the client's own retry replays the identical batch.

### 🔴 Senior

**Q:** What does the outbox guarantee, what does it not, and how did you test the guarantee in the Java version?

**A:** It guarantees that a change and its announcement exist together or not at all, and it guarantees nothing about delivery count or delivery order. In StreamPulse the outbox port is `Propagation.MANDATORY`, so calling it with no transaction throws instead of opening one that would commit on its own, and ADR-0015 records that mutating it to `REQUIRES_NEW` turns two of the atomicity tests red. `OutboxAtomicityIT` rolls back after the announcement was written and asserts zero tenants and zero outbox rows, and the test first asserts the row is visible inside the transaction so it is not vacuous. A second test adds a CHECK constraint that makes the outbox insert fail and asserts the business change rolled back too. The gaps are real: no retention job exists for the outbox table, nothing alerts on relay lag (both from ADR-0015), and my FieldSync integration test checks event counts for applied and stale writes but does not force a mid-transaction failure.

**Source:** `streampulse/services/control-plane/src/main/java/com/streampulse/controlplane/adapter/out/outbox/JdbcConfigChangeOutbox.java:31-47`

```java
    /**
     * MANDATORY, not REQUIRED: called with no transaction this throws instead of opening one that
     * would commit on its own. REQUIRES_NEW here would let the row outlive a rolled-back change.
     */
    @Override
    @Transactional(propagation = Propagation.MANDATORY)
    public void append(ChangeEvent event) {
        jdbc.sql(INSERT)
                .param("id", event.changeId())
                .param("type", event.kind().name())
                .param("key", event.entityId())
                .param("tenant", event.tenantId())
                .param("operation", event.operation().name())
                .param("payload", encoder.encode(event), Types.BINARY)
                .param("createdAt", OffsetDateTime.ofInstant(event.changedAt(), ZoneOffset.UTC))
                .update();
    }
```

**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxAtomicityIT.java:81-97`

```java
    @Test
    @DisplayName("a change that rolls back after its announcement was written leaves NO outbox row")
    void rolledBackChangeLeavesNoOutboxRow() {
        var tx = new TransactionTemplate(txManager);

        assertThatThrownBy(() -> tx.executeWithoutResult(status -> {
                    tenants.create(acme());
                    assertThat(count("outbox"))
                            .as("the row is really there, inside the transaction: the test is not vacuous")
                            .isEqualTo(1);
                    throw new IllegalStateException("abandon the unit of work");
                }))
                .isInstanceOf(IllegalStateException.class);

        assertThat(count("tenant")).isZero();
        assertThat(count("outbox")).isZero();
    }
```

**Follow-up they will ask:** What is the throughput and latency ceiling of your polling relay?

**A:** There are two configurations and the numbers differ. The local-dev loop ticks every 5 seconds (from `cmd/outbox-relay/main.go`), takes 25 rows per tick and calls `PutEvents` once per row, so by arithmetic it publishes at most about 5 events per second with up to roughly 5 seconds of added latency. The Terraform schedule for the AWS entrypoint is `rate(1 minute)` with one `RunOnce` per invocation, so there the ceiling is 25 events per minute, about 0.4 per second, with up to a minute of latency. Both figures are derived from constants I read, not measured, and I did not verify that the Terraform was applied. That is acceptable for a field-survey app, and the migration comment says no CDC is needed at this scale. If volume grew I would loop inside an invocation until the backlog drains, use the multi-entry `PutEvents` call, or move to Debezium as I did in StreamPulse. I would also fix the ordering column, because my FieldSync relay orders by `occurred_at`, while ticket-booking added a `BIGSERIAL outbox_seq` after a real bug (Phase 6).

## Phase 4 — Change data capture with Debezium (outbox router, tombstones, keys and partitions)

### 🟢 Beginner

**Q:** What is change data capture, and why use it for an outbox?

**A:** Change data capture reads the database's write-ahead log and turns committed row changes into events, so the application does not need a polling loop. In StreamPulse the Debezium Postgres connector reads the `control_plane.outbox` table through a replication slot and publishes to the `config.changes.v1` Kafka topic. The application only ever inserts a row in its own transaction, and Debezium does the publishing. ADR-0016 also records the alternative I did not build, a polling publisher inside the service, which is simpler to run but adds polling latency.

### 🟡 Intermediate

**Q:** Walk me through the connector configuration: key, payload, topic and tombstone.

**A:** The outbox router takes the Kafka key from `aggregate_id`, the value from the `payload` column, and routes every row to the single topic `config.changes.v1` regardless of `aggregate_type`. The payload column is `bytea` holding raw Avro, so the value converter is the byte-array converter and the key converter is the string converter. A NULL payload becomes a null-value record because `route.tombstone.on.empty.payload` is true, and that is how a delete reaches a compacted topic. The additional placement setting copies the `operation` column into a header named `operation` and the `aggregate_type` column into a header named `entityKind`. The connector file is the same one the compose stack registers and the same one the integration test uses, so the test and the stack cannot drift.

**Source:** `streampulse/docker/debezium/outbox-connector.json:14-35`

```json
    "plugin.name": "pgoutput",
    "slot.name": "control_plane_outbox",
    "publication.name": "control_plane_outbox_pub",
    "publication.autocreate.mode": "filtered",
    "table.include.list": "control_plane.outbox",

    "tombstones.on.delete": "false",

    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.converters.ByteArrayConverter",

    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.field.event.key": "aggregate_id",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.route.by.field": "aggregate_type",
    "transforms.outbox.route.topic.regex": ".*",
    "transforms.outbox.route.topic.replacement": "config.changes.v1",
    "transforms.outbox.route.tombstone.on.empty.payload": "true",
    "transforms.outbox.table.fields.additional.placement": "operation:header:operation,aggregate_type:header:entityKind"
  }
```

When I present this I name the coupling: the column names in the outbox migration are the router's configuration, so renaming `payload` or `aggregate_id` breaks the connector silently, and the migration carries a comment saying so.

**Q:** How do you prove the CDC path end to end?

**A:** `OutboxCdcIT` starts Postgres with `wal_level=logical`, Kafka and Debezium Connect in Testcontainers, registers the real connector file, then creates, updates and deletes one tenant. It reads the topic from the beginning and asserts three records on one key in one partition with increasing offsets. The first two decode as Avro `ConfigChange` records with operations CREATED and UPDATED, and the third has a null value. It also asserts that each record's `changeId` equals its outbox row id, which is what a consumer uses to deduplicate a replay.

**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java:145-152`

```java
        List<ConsumerRecord<String, byte[]>> records = recordsForKey("tenant/cdc-tenant", 3);

        assertThat(records).hasSize(3);
        assertThat(records)
                .extracting(ConsumerRecord::partition)
                .as("one key, one partition")
                .containsOnly(records.getFirst().partition());
        assertThat(records).extracting(ConsumerRecord::offset).isSorted();
```

**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java:165-167`

```java
        assertThat(records.get(2).value())
                .as("a delete is a tombstone: null value")
                .isNull();
```

### 🔴 Senior

**Q:** What are the failure modes of the Debezium relay, and what did you observe?

**A:** The first failure mode is the connector being down: the control plane kept accepting changes (ADR-0016 records 201 and 200 responses while Connect was stopped), outbox rows accumulated, and Postgres retained write-ahead log for the inactive replication slot. An abandoned slot would eventually fill the disk, so a retired connector needs `pg_drop_replication_slot`, and I have no alert on slot lag. The second is at-least-once delivery after a connector restart, so consumers use `changeId` and `version` to ignore duplicates. The third is that ordering holds per key only, so a consumer must not assume a tenant's record precedes its title's. The fourth is compaction: a tombstone is kept for `delete.retention.ms` and then removed, so a consumer that starts later sees neither the key nor its deletion. The one run I recorded gave three records at offsets 0, 1 and 2, with Avro payloads of 210 and 214 bytes (observed once, ADR-0016); I did not benchmark throughput or end-to-end latency, and these behaviours were observed on image `3.0.8.Final`, so verify them against current Debezium docs when upgrading.

**Source:** `streampulse/api/asyncapi/streampulse-topics.yaml:103-114`

```yaml
      **Key: `entityId`. Cleanup policy: COMPACT.**

      This is the one topic where compaction is the point. Consumers rebuild a cache from
      it at startup, so they need the *current* value of every key — not the history of
      changes. Compaction keeps the last record per key indefinitely at bounded size.

      Two consequences that follow from compaction and are easy to get wrong:
        - The payload must be a FULL SNAPSHOT, never a delta. After compaction the
          intermediate records are gone, so a consumer replaying from the start would
          apply a diff to a state it never saw.
        - A delete is published as a null-payload TOMBSTONE. That is how a compacted topic
          actually forgets a key.
```

**Follow-up they will ask:** Why is the payload a full snapshot and why is the key the entity id?

**A:** The topic is compacted, so after compaction the intermediate records are gone and a consumer replaying from the start would apply a delta to a state it never saw. A full snapshot per key makes the last record per key sufficient to rebuild a cache. The key is the entity id so that all changes to one entity land on one partition in order, which is the only ordering Kafka gives. The cost is that I cannot reconstruct history from this topic, so the outbox table in Postgres remains the audit trail.

## Phase 5 — Consumers, retries, poison messages and dead letters

### 🟢 Beginner

**Q:** What happens in your original FieldSync consumer when the handler fails?

**A:** The failed event is simply not marked processed, so the next tick selects it again and retries it, and the rest of the batch continues. That is at-least-once and it is safe for a transient error such as a database blip. The honest weakness is that the loop has no attempt counter and no dead-letter path, so a permanently bad event is retried forever. Dead-lettering exists in later code, the two-way sync package, and not in this original consumer.

**Source:** `GolangExercise/offline-sync-app/internal/consume/consume.go:36-49`

```go
	processed := 0
	for _, evt := range events {
		if err := handle(ctx, evt); err != nil {
			log.Printf("%s: handle event %s failed, will retry next tick: %v", consumerName, evt.ID, err)
			continue
		}
		if err := q.MarkEventProcessed(ctx, db.MarkEventProcessedParams{
			EventID:      evt.ID,
			ConsumerName: consumerName,
		}); err != nil {
			return processed, fmt.Errorf("mark event %s processed by %s: %w", evt.ID, consumerName, err)
		}
		processed++
	}
```

**Q:** What is a poison message and what is a dead-letter queue?

**A:** A poison message is one that can never be processed successfully, for example a body that is not valid JSON, so retrying it only burns capacity and blocks work behind it. A dead-letter queue or table is where I park such a message with its raw bytes, the reason and the attempt count, so the main flow keeps moving and a human can inspect it later. In Kafka the poison record sits in front of the offset, so without a dead letter one bad record stops its whole partition.

### 🟡 Intermediate

**Q:** How does your webhook worker cap retries and dead-letter?

**A:** Each failure runs in its own transaction that increments `attempts` and stores `last_error`, and when attempts reach the configured maximum it inserts a row into `sync_dead_letters` with the raw body, the reason and the attempt count, then marks the inbox row dead so it is no longer selected. The raw body is stored as bytes because a poison body may not be valid JSON. The integration test sends a validly signed body of `not json` and asserts exactly 3 attempts, a reason and the raw body, and it asserts that attempts stop growing afterwards. The loader makes the same decision for pushes: exhausted retries and permanent 4xx responses dead-letter, while anything else, such as a cancelled context, is returned so the event stays unprocessed.

**Source:** `GolangExercise/offline-sync-app/internal/webhook/worker.go:100-119`

```go
	row, err := q.RecordInboxFailure(ctx, db.RecordInboxFailureParams{System: w.system, DeliveryID: deliveryID, LastError: cause.Error()})
	if err != nil {
		return fmt.Errorf("record inbox failure: %w", err)
	}
	if row.Attempts >= w.maxAttempts {
		if err := q.InsertDeadLetter(ctx, db.InsertDeadLetterParams{
			Source:   "inbox",
			System:   w.system,
			RefID:    deliveryID,
			Payload:  row.Body,
			Reason:   cause.Error(),
			Attempts: row.Attempts,
		}); err != nil {
			return fmt.Errorf("insert dead letter: %w", err)
		}
		if err := q.MarkInboxDead(ctx, db.MarkInboxDeadParams{System: w.system, DeliveryID: deliveryID}); err != nil {
			return fmt.Errorf("mark inbox dead: %w", err)
		}
		log.Printf("webhook-worker %s: delivery %s dead-lettered after %d attempts: %v", w.system, deliveryID, row.Attempts, cause)
	}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/loader.go:80-91`

```go
func (l *Loader) onPushError(ctx context.Context, evt db.DomainEvent, err error) error {
	var exhausted *RetryExhaustedError
	var api *APIError
	switch {
	case errors.As(err, &exhausted):
		return l.deadLetter(ctx, evt, exhausted.Attempts, err)
	case errors.As(err, &api) && !api.retryable():
		return l.deadLetter(ctx, evt, 1, err)
	default:
		return fmt.Errorf("push event %s: %w", evt.ID, err)
	}
}
```

I tell the interviewer what is not solved: the docs list no backoff between inbox retries, so a poison body burns the same attempts as a transient error, and there is no replay tooling or alert on dead-letter growth.

### 🔴 Senior

**Q:** How does the Kafka sink tell a poison record from a store outage, and why does it never dead-letter after N attempts?

**A:** A poison record and an outage need opposite handling, so the sink separates them. Records that cannot be decoded go to the dead-letter topic with the original bytes, the original key and a `dlt-reason` header, and the listener still acknowledges past them. When a batch keeps failing, the batch writer retries it, then writes the records one at a time: if some succeed the store is up and the failures are poison, and if none succeed it cannot tell, so it treats the failure as an outage and fails every record. An outage is retried with exponential backoff, 1 second doubling to 30 seconds (from config), with no attempt or elapsed-time limit, and the recoverer deliberately throws "refusing to skip", because dead-lettering healthy records during an outage would turn it into data loss. `PoisonRecordIT` sends 5 good records, 2 garbage records and 5 more good ones, and asserts 10 stored rows, committed offsets totalling 12, exactly two dead letters keyed `poison-1` and `poison-2`, and a counter of 2. The boundary is stated in ADR-0013: a poison record alone in its batch cannot be told from an outage by the isolation rule, so the decoder rejects the common deterministic causes first, and the test ran on a single-broker Testcontainers setup.

**Source:** `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/config/SinkConfig.java:152-166`

```java
    static DefaultErrorHandler neverGiveUpErrorHandler(BackOff backOff) {
        // The recoverer is what DefaultErrorHandler calls to SKIP a record. Skipping is exactly what
        // this sink must never do, so it refuses; poison records are dead-lettered by the listener.
        var handler = new DefaultErrorHandler(
                (record, exception) -> {
                    throw new IllegalStateException(
                            "refusing to skip " + record.topic() + "-" + record.partition() + "@" + record.offset(),
                            exception);
                },
                backOff);
        // Spring treats some exception types as "not retryable" and skips straight to the recoverer.
        // Here every exception is retried.
        handler.setClassifications(Map.of(), true);
        return handler;
    }
```

**Source:** `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java:260-280`

```java
    private void isolate(List<Pending<T>> batch, Exception batchFailure) {
        var failed = new ArrayList<Failed<T>>();
        for (Pending<T> pending : batch) {
            long start = System.nanoTime();
            try {
                sink.write(List.of(pending.value()));
                metrics.flushed(1, Duration.ofNanos(System.nanoTime() - start));
                pending.future().complete(null);
            } catch (Exception e) {
                metrics.flushFailed();
                failed.add(new Failed<>(pending, e));
            }
        }
        if (failed.size() == batch.size()) {
            failAll(batch, batchFailure);
            return;
        }
        for (Failed<T> f : failed) {
            deadLetter(f);
        }
    }
```

**Follow-up they will ask:** Where in your own code is a bad message dropped without a dead letter?

**A:** In the ticket-booking projector: an unrecognised event type, a malformed payload or an unknown seat ordinal is logged and then marked processed, so the event is skipped for good with only a log line as evidence. I chose that so one bad row cannot stall the read model, but it is a silent drop and I would add a dead-letter table and a counter before calling it production-ready. The same file shows the opposite choice for a Redis failure: the event is left unprocessed so it retries, because marking it processed would leave a permanent hole in the bitset.

**Source:** `GolangExercise/ticket-booking/internal/projector/projector.go:183-188`

```go
		var payload domainEventPayload
		if err := json.Unmarshal(evt.Payload, &payload); err != nil {
			log.Printf("projector: skipping event %s: malformed payload: %v", evt.EventID, err)
			p.markProcessed(ctx, evt.EventID)
			continue
		}
```

On AWS, the Terraform in `offline-sync-app/infra/terraform/modules/eventing/main.tf` defines an SQS dead-letter queue per consumer with `maxReceiveCount = 5` and 14-day retention, and the Lambda event source mapping uses `ReportBatchItemFailures` so only failed messages are redelivered. That is configuration I read, and I did not verify that it was applied to an account.

## Phase 6 — Ordering, partitions and consumer lag

### 🟢 Beginner

**Q:** Does Kafka keep messages in order?

**A:** Only within a single partition. Messages with the same key go to the same partition, so they stay in order for that key, but there is no ordering across different keys. In StreamPulse the raw telemetry topic is keyed by `sessionId`, so one viewing session's events stay in order, while ordering between two sessions is not promised.

**Q:** What is consumer lag?

**A:** It is how far a consumer group's committed offset is behind the end of the log, per partition. In my sink the offset is acknowledged only after the durable write, so lag means work not yet stored, which is the meaning I want. I read it per partition, because one lagging partition points to a hot key while all partitions lagging points to a slow consumer or store.

### 🟡 Intermediate

**Q:** How did you choose partition keys, and what does the choice cost?

**A:** I wrote the choice and the rejected alternatives into the AsyncAPI contract. Raw telemetry is keyed by `sessionId`, because `tenantId` would give three hot partitions with only three tenants and a null key would give no ordering at all. The cost I accept is that aggregating per title needs a repartition, which is a network hop and an extra topic, because ordering is a correctness property and repartitioning is a performance cost. The topic has 12 partitions, which caps consumer parallelism and divides evenly by 1, 2, 3, 4, 6 and 12, and raising the count later rehashes keys and breaks ordering.

**Source:** `streampulse/api/asyncapi/streampulse-topics.yaml:31-45`

```yaml
      **Key: `sessionId`.** All events for one viewing session land on one partition, which
      is the only way Kafka gives ordering — and `session_start → heartbeat → buffering →
      session_end` must stay ordered for stream processing to be correct.

      Rejected alternatives:
        - `tenantId` — only three tenants, so three hot partitions and the rest idle.
        - `null` (round-robin) — perfect balance, no ordering at all.

      The cost we accept: aggregating per *title* needs a repartition, which is a network
      hop and an extra topic. Ordering is a correctness property; repartitioning is a
      performance cost. That is the trade.

      **12 partitions.** Partition count is the ceiling on consumer-group parallelism, and
      raising it later rehashes keys and BREAKS ordering — so pick above current need. 12
      divides by 1, 2, 3, 4, 6 and 12, so consumers scale evenly.
```

**Q:** In the Go projects, where does ordering matter and how is it enforced?

**A:** In ticket-booking the projector applies seat transitions to a Redis bitset, so applying two same-direction transitions out of their real order silently no-ops the second one through its own idempotency check. A test that applied 220 real transitions produced only 112 applied changes, which exposed that `created_at` is not a strict total order, so I added a `BIGSERIAL outbox_seq` and ordered by it (the migration comment records those numbers). The relay does not care about delivery order, but the projector does. In FieldSync I avoid depending on delivery order at the data layer instead, with an atomic version gate in SQL that applies an incoming external version only if it is strictly newer. One gap remains: my FieldSync relay and consumer queries still order by `occurred_at`.

**Source:** `GolangExercise/ticket-booking/sqlc/queries.sql:314-327`

```sql
-- name: ListUnprocessedDomainEvents :many
SELECT de.event_id, de.aggregate_id, de.event_type, de.schema_version, de.payload, de.created_at
FROM domain_events de
WHERE de.event_type IN ('seat.held', 'seat.released', 'seat.booked')
  AND NOT EXISTS (
    SELECT 1 FROM processed_events pe
    WHERE pe.event_id = de.event_id AND pe.consumer_name = sqlc.arg(consumer_name)
  )
-- outbox_seq, NOT created_at (migration 0008): created_at alone is not a
-- strict total order under rapid sequential inserts, and this consumer's
-- correctness genuinely depends on applying transitions in real order —
-- unlike the outbox relay, which doesn't care about delivery order.
ORDER BY de.outbox_seq
LIMIT sqlc.arg(row_limit);
```

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:146-152`

```sql
-- name: AdvanceLinkVersion :one
-- Atomic version gate: 0 rows (pgx.ErrNoRows) unless the incoming external
-- version is strictly newer than the last applied one. Also row-locks the
-- link until the surrounding transaction ends.
UPDATE external_id_map SET last_version = sqlc.arg(version)
WHERE system = $1 AND external_id = $2 AND last_version < sqlc.arg(version)
RETURNING *;
```

### 🔴 Senior

**Q:** The aggregate-topic lag is climbing. Walk me through the diagnosis and the limits of scaling.

**A:** I ask three questions in order: which topic's lag is it, since raw-topic lag means the stream processor is behind and aggregate-topic lag means the sink is behind; is it one partition or all, since one partition is a hot key and more consumers will not help; and what is the batch writer's queue depth, since near its 2,000 capacity means Postgres is slow and near empty with growing lag means consumers are starved or rebalancing. The ceilings come from partitions: the aggregate topic has 6 partitions and the sink runs 3 threads (both from config and the AsyncAPI file), so I have exactly 2x headroom and then a wall. Backpressure is the signal by design: a full buffer fails `submit` after 1 second, the listener throws without acknowledging, redelivery backs off from 1 to 30 seconds, and lag rises. `max.poll.interval.ms` is 300,000, deliberately above the 30-second poll budget plus the 30-second maximum backoff, and a wiring test asserts that inequality. What I actually observed was lag of 1 on each of the 6 partitions with the sink idle after a 90-second run, which I believe is the transaction commit marker of the exactly-once producer but did not confirm by dumping the log. I did not measure peak lag or drain time under load, and autoscaling on lag is not built.

**Source:** `streampulse/services/sink-writer/src/main/resources/application.yml:36-55`

```yaml
    consumer:
      group-id: sink-writer
      # The offset is committed by the listener, after the durable write, never on a timer.
      enable-auto-commit: false
      # A new group must read the whole topic, not only what arrives after it joins.
      auto-offset-reset: earliest
      max-poll-records: 500
      # Skip records of aborted producer transactions (the stream processor is exactly-once v2).
      isolation-level: read_committed
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.ByteArrayDeserializer
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
        # Must exceed the poll budget (30 s) plus the longest error-handler backoff (30 s) and the
        # worst flush retry, or the broker evicts the consumer in the middle of an outage.
        max.poll.interval.ms: 300000
    listener:
      type: batch
      ack-mode: manual
      concurrency: 3
```

**Follow-up they will ask:** If the sink consumes partitions in parallel and in batches, how can it be correct without ordering?

**A:** It does not rely on arrival order; it relies on a guard in the write. The upsert only replaces a row whose stored `computed_at` is older than or equal to the incoming one, so reordering and replays cannot move a value backwards, and the key is the aggregate's identity so a redelivery overwrites itself. I would not use the same trick for data where every intermediate state matters, such as a ledger, where per-key ordering and a single writer per key would be needed. An alert on "lag greater than 0" would fire forever on this transactional topic given the observed lag of 1, so the alert should look at lag growing or above a small constant. The repo's observability notes describe the lag alert that way, but I have not verified that rule file or run its tests.

## Phase 7 — Testing reliability (integration tests, poison-record tests, crash scenarios)

### 🟢 Beginner

**Q:** Why test reliability with a real database or broker and not only mocks?

**A:** Reliability properties live in the interaction, such as transaction boundaries, unique constraints and offset commits, and a mock cannot reproduce them. In FieldSync the relay's control flow is unit-tested against a hand-written fake publisher, while the atomic SQL and the transaction are tested against real Postgres under the `integration` build tag. In StreamPulse the integration tests start real Kafka, Postgres, Redis and Debezium in Testcontainers. I keep both layers because the unit tests are fast and the integration tests are the ones that prove the failure paths.

### 🟡 Intermediate

**Q:** How do you unit test the relay's failure behaviour?

**A:** I give the relay a fake publisher that can return an error or a rejected entry, and a mocked Querier from gomock with no expectation for `MarkEventPublished` on the failure path, so gomock fails the test if the relay marks a failed event published. Other tests assert that a failed first entry does not stop the second, and that a rejected entry inside a successful call is not marked either. The same tests are the evidence for the at-least-once claim in Phase 1.

**Source:** `GolangExercise/offline-sync-app/internal/outbox/relay_test.go:67-86`

```go
// TestRelay_RunOnce_LeavesUnmarkedOnPublishFailure covers the safety-net
// behavior: a transient EventBridge failure must NOT mark the event
// published — it has to still be there for the next tick.
func TestRelay_RunOnce_LeavesUnmarkedOnPublishFailure(t *testing.T) {
	ctrl := gomock.NewController(t)
	q := mocks.NewMockQuerier(ctrl)
	evt := sampleEvent(uuid.New())

	q.EXPECT().ListUnpublishedEvents(gomock.Any(), int32(25)).Return([]db.DomainEvent{evt}, nil)
	// No MarkEventPublished expectation — gomock fails the test if it's called.

	relay := NewRelay(q, &fakePublisher{failNext: true}, "fieldsync-events")
	published, err := relay.RunOnce(context.Background())
	if err != nil {
		t.Fatalf("RunOnce() error = %v", err)
	}
	if published != 0 {
		t.Errorf("published = %d, want 0", published)
	}
}
```

When I describe this test I name the technique: absence of an expected call is the assertion.

### 🔴 Senior

**Q:** How do you test a crash, and what does that test not prove?

**A:** I inject the crash at the exact point I am worried about. In FieldSync a transactor wrapper runs the page's work and then returns "simulated crash after apply, before commit" on the second call, and the test asserts that only page 1 is applied, the checkpoint points at page 2's cursor, and the resumed run fetches from that cursor and ends with 7 links, 7 events and zero work items with more than one event. In StreamPulse a test-only `PreAckHook` throws after the durable write and before the acknowledgement, three times, and the test asserts 60 rows, unchanged values, committed offsets of 60, more write attempts than records (so redelivery really happened), and an empty dead-letter topic. Neither test kills a process: both inject an exception, and ADR-0013 and the test's own javadoc say a broker or Postgres failing mid-write and a killed JVM are not covered. The idempotent upsert is what makes a real crash safe, but I have not demonstrated it with a kill signal. The Debezium restart case I observed by hand (ADR-0016) rather than automated.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:543-563`

```go
type crashBeforeCommitTx struct {
	pool        *pgxpool.Pool
	crashOnCall int
	calls       int
}

func (c *crashBeforeCommitTx) InTx(ctx context.Context, fn func(q db.Querier) error) error {
	c.calls++
	if c.calls != c.crashOnCall {
		return NewPgxTransactor(c.pool).InTx(ctx, fn)
	}
	tx, err := c.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if err := fn(db.New(tx)); err != nil {
		return err
	}
	return errors.New("simulated crash after apply, before commit")
}
```

**Source:** `streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/NoLossNoDoubleCountIT.java:91-103`

```java
    @TestConfiguration
    static class FaultInjection {
        @Bean
        @Primary
        PreAckHook failAfterTheWriteBeforeTheAck() {
            return () -> {
                if (FAILURES_LEFT.getAndDecrement() > 0) {
                    FAILURES_INJECTED.incrementAndGet();
                    throw new IllegalStateException("injected: after the durable write, before the ack");
                }
            };
        }
    }
```

**Follow-up they will ask:** How do you test poison records, and how do you know a test can fail?

**A:** `PoisonRecordIT` interleaves two garbage records between healthy ones and asserts the three things that matter: healthy rows are stored, the poison bytes arrive on the dead-letter topic untouched with the key and a `dlt-reason`, and the committed offset total includes the poison records so the group is not blocked. To know a test can fail I mutate the code: the two-way sync doc records a by-hand mutation check where removing dead-lettering, the checkpoint write or the version gate each turned at least one test red, and `IngestServiceTest` records that a single-shot concurrency test passed against a deliberately broken check-then-set store, so the final version loops 200 iterations with 8 threads (constants in the test) and was verified to fail against that broken store. Repetition raises the hit probability of a race but cannot prove its absence.

**Source:** `streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/PoisonRecordIT.java:93-112`

```java
        await().atMost(Duration.ofSeconds(90)).untilAsserted(() -> {
            assertThat(jdbc.queryForObject("SELECT count(*) FROM metric_window", Integer.class))
                    .isEqualTo(10);
            assertThat(ItSupport.committedOffsetTotal(KAFKA.getBootstrapServers(), "sink-writer"))
                    .as("the poison records are acknowledged too, so they do not block the group")
                    .isEqualTo(12);
        });

        var dead = ItSupport.readAll(KAFKA.getBootstrapServers(), DLT);
        assertThat(dead).hasSize(2);
        assertThat(dead).extracting(r -> r.key()).containsExactlyInAnyOrder("poison-1", "poison-2");
        var first = dead.stream()
                .filter(r -> r.key().equals("poison-1"))
                .findFirst()
                .orElseThrow();
        assertThat(first.value()).isEqualTo(garbage);
        assertThat(new String(first.headers().lastHeader("dlt-reason").value(), StandardCharsets.UTF_8))
                .contains("decode");
        assertThat(meters.get("streampulse.sink.dead.letters").counter().count())
                .isEqualTo(2.0);
```

## Code reference index

| path:lines | what it shows |
|---|---|
| `GolangExercise/offline-sync-app/internal/outbox/relay.go:62-107` | Relay `RunOnce`: list unpublished, `PutEvents`, check `FailedEntryCount`, mark published |
| `GolangExercise/offline-sync-app/internal/events/events.go:34-52` | `Publish` writes the `domain_events` row with the caller's transaction-bound Querier |
| `GolangExercise/offline-sync-app/internal/sync/transactional.go:37-102` | `TxRunner`: upserts plus events only for Applied records, one commit |
| `GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql:5-28` | `domain_events` outbox table, partial index, `processed_events` dedupe table |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:49-60` | Relay and dedupe queries; ordered by `occurred_at` |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:87-96` | `ListUnprocessedEventsForConsumer`: anti-join on `processed_events` |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:201-236` | Inbox, claim with `SKIP LOCKED`, failure counter, dead letters |
| `GolangExercise/offline-sync-app/internal/consume/consume.go:26-51` | Shared consumer loop; failed event retried next tick, no cap |
| `GolangExercise/offline-sync-app/internal/sqsconsume/sqsconsume.go:27-79` | SQS handler with dedupe check and partial-batch failure response |
| `GolangExercise/offline-sync-app/internal/webhook/worker.go:37-124` | Per-row transaction, `SKIP LOCKED`, attempts and dead-lettering |
| `GolangExercise/offline-sync-app/internal/twoway/loader.go:37-106` | Event id as idempotency key; permanent vs exhausted vs transient errors |
| `GolangExercise/offline-sync-app/internal/twoway/client.go:108-153` | Retry loop, `Retry-After`, full-jitter backoff |
| `GolangExercise/offline-sync-app/docs/two-way-sync.md:87` | `sync_dead_letters` design choice |
| `GolangExercise/offline-sync-app/docs/two-way-sync.md:157-171` | What is not solved: no backoff on inbox retries, no replay tooling |
| `GolangExercise/offline-sync-app/internal/outbox/relay_test.go:67-137` | Relay failure tests with a fake publisher |
| `GolangExercise/offline-sync-app/internal/sync/integration_test.go:117-174` | Event row exists for Applied, none for ignored-stale |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:333-421` | Poison dead letter, loader exhaustion, crash mid-backfill |
| `GolangExercise/offline-sync-app/infra/terraform/modules/eventing/main.tf:30-44` | SQS DLQ and `maxReceiveCount = 5` (config read, not applied) |
| `GolangExercise/offline-sync-app/cmd/outbox-relay/main.go:38-50` | Local-dev 5 second ticker driving `RunOnce` |
| `GolangExercise/offline-sync-app/infra/terraform/modules/eventing/main.tf:229-230` | AWS schedule for the relay: `rate(1 minute)` (config read, not applied) |
| `GolangExercise/ticket-booking/internal/outbox/relay.go:56-95` | The Go relay in the ticketing project |
| `GolangExercise/ticket-booking/internal/projector/projector.go:166-210` | Projector loop: skip bad events, leave Redis failures unprocessed |
| `GolangExercise/ticket-booking/migrations/000008_domain_events_outbox_seq.up.sql:1-16` | The ordering bug and the `outbox_seq` fix |
| `GolangExercise/ticket-booking/internal/order/order.go:304-310` | Deterministic charge idempotency key |
| `streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java:46-92` | Client-generated id, validation, tenant-namespaced Redis key |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java:138-191` | Claim, publish, release on failure, fail open |
| `streampulse/services/ingest-gateway/src/main/resources/application.yml:186` | `idempotency-ttl: 24h` |
| `streampulse/docs/adr/0007-fail-open-on-idempotency-store-failure.md` | Fail-open decision and when it would be wrong |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/adapter/out/postgres/JdbcMetricWindowStore.java:19-31` | Idempotent upsert guarded by `computed_at <=` |
| `streampulse/docs/adr/0013-sink-durable-then-commit.md` | Durable-then-commit, poison vs outage, rejected alternatives |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/adapter/in/kafka/AggregateBatchListener.java:66-81` | Decode, submit, wait for all, then acknowledge |
| `streampulse/services/control-plane/src/main/resources/db/migration/V1__control_plane.sql:70-81` | The outbox table whose columns configure the router |
| `streampulse/docs/adr/0015-jpa-flyway-transactional-outbox.md` | Why not dual write; guarantees and gaps |
| `streampulse/docs/adr/0016-debezium-outbox-router-raw-avro.md` | Connector settings, observed evidence, what breaks |
| `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxCdcIT.java:133-173` | CDC test: three records, one partition, tombstone, changeId |
| `streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/PoisonRecordIT.java:79-113` | Poison records dead-lettered, group not blocked |
| `streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/application/IngestServiceTest.java:400-453` | Release-on-failure test and the bug it guards |
| `streampulse/docs/deep-dive.md:443-474` | Consumer lag playbook, ceilings, observed lag of 1 |

## Self-check

1. Where exactly can a duplicate enter the FieldSync relay? After `PutEvents` succeeds and before `MarkEventPublished` commits, so the row is published again on the next tick.
2. Why must the dedupe claim commit together with the side effect? Because a crash between them either loses the effect or repeats it, and only one transaction closes that gap.
3. Why does the sink never dead-letter after N failed attempts? Because that turns a store outage into data loss for records that were never bad.
4. Why is the Debezium payload a full snapshot with the entity id as key? Because the topic is compacted, so only the last record per key survives, and the key keeps one entity's changes on one partition in order.
5. What do the crash tests not prove? They inject exceptions, not process kills, and they do not cover a broker or Postgres failing mid-write.

## What not to claim

- Do not say the pipeline is exactly-once; say at-least-once delivery plus idempotent processing, with Kafka Streams `exactly_once_v2` covering Kafka to Kafka only.
- Do not say the original FieldSync consumer dead-letters; it retries forever, and dead-lettering exists in `webhook.Worker` and `twoway.Loader`.
- Do not say the SQS dead-letter queue is running; the Terraform exists and I did not verify an applied deployment.
- Do not quote throughput, relay latency, peak consumer lag or drain time as measured; the 5 events per second (local) and 0.4 per second (Terraform schedule) figures are derived from constants and peak lag was not measured.
- Do not say the Redis claim is crash-safe; a crash between the claim and the publish can swallow the client's retry for the 24 hour TTL.
- Do not say the outbox table is maintained; no retention job exists and nothing alerts on relay or replication-slot lag.
- Do not say the ticket-booking projector dead-letters bad events; it logs and marks them processed.
- Do not state Debezium or Kafka behaviour beyond what the connector file, the tests and ADR-0016 show without saying "verify in current docs", for example tombstone retention and how `tombstones.on.delete` interacts with the router.
- Do not claim these tests were run recently; read the test source, then run them yourself before the interview.
