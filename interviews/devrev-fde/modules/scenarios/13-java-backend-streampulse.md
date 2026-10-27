# Scenarios 13 — Java backend (Spring, Kafka, testing) via streampulse

Source module: [`../13-java-backend-streampulse.md`](../13-java-backend-streampulse.md). Six real-time situations an FDE meets, laddered 🟢 🟢 🟡 🟡 🔴 🔴.

How to use: read only the **Situation**, answer out loud, then compare. Every number in a Situation is an **example** to make the story concrete, not a measurement from my repo. Numbers that come from the repo's own records are marked "from the repo's notes" and are from one developer machine (Apple M2 Pro, a single Kafka broker, replication factor 1, load generator sharing the CPU), not production figures.

Lanes: **[P]** shipped at Couchbase · **[L]** my own build · **[K]** knowledge only, not built.

streampulse is a learning and portfolio system, so every file link below is **[L]** and nothing was ever deployed for a customer. Some commits are co-authored with Claude, so I must defend each line from the code. The repo lives in a sibling folder, `GitHub/streampulse`; the links below resolve from this folder to it.

| # | Level | Failure mode |
|---|---|---|
| 1 | 🟢 | A Spring bean wiring failure at startup after a config change |
| 2 | 🟢 | The OpenAPI says 413 for an oversized batch and the API returns 400 |
| 3 | 🟡 | Kafka consumer lag grows on the sink writer |
| 4 | 🟡 | Throughput plateaus and 503s appear while CPU is low: is it virtual-thread pinning? |
| 5 | 🔴 | A record-type migration breaks a consumer during a mixed-version rollout |
| 6 | 🔴 | A processor restart silently drops on-time events from the aggregates |

---

## Scenario 1 🟢 The ingest gateway will not start after the customer changes one property

**Situation.** Monday 08:50, a customer's platform team rolls out a new config for the ingest gateway (example). They set `STREAMPULSE_BACKBONE=msk` because they run a managed Kafka service. The pod crash-loops. The log ends with an `APPLICATION FAILED TO START` block saying a parameter of `ingestUseCase` in `IngestConfig` required a bean of type `EventPublisher` that could not be found (the shape of Spring's message, example).

**Level.** 🟢 Beginner.

**What's being tested.** Dependency injection and a hand-written composition root, conditional beans, how startup failures read, and why a missing bean fails at startup and not at the first request.

**Clarifying questions to ask first.**
1. What changed in this release: code, config, or environment variables?
2. What exactly is in the startup failure: the first `Caused by` and the bean named in the Description?
3. Which property selects the event backbone, and what are its allowed values?
4. Did it ever start with the old config? Is it only this environment?
5. Do we have a context-assembly test for this service in CI?

**Flow of control and data.**

```
env STREAMPULSE_BACKBONE=msk ─▶ Environment property streampulse.backbone = "msk"
IngestConfig @Bean kinesisEventPublisher  @ConditionalOnProperty(havingValue = "kinesis")            ─▶ no match
IngestConfig @Bean kafkaEventPublisher    @ConditionalOnProperty(havingValue = "kafka", matchIfMissing = true)
        ─▶ matchIfMissing applies only when the property is ABSENT; "msk" is present and different ─▶ no match
ingestUseCase(EventPublisher, ...) needs the port ─▶ no bean ─▶ context refresh fails ─▶ process exits
```

**Diagnosis steps.**
1. Read the first failure block, not the stack. The `Description` names the consumer, the type and the parameter; the `Action` says what is missing.
2. Look at the effective value of the property in the running environment. The environment variable maps to `streampulse.backbone` by Spring's relaxed binding.
3. Start the service with the condition evaluation report enabled (`--debug`, verify the exact flag in current Spring Boot docs). It lists both publisher beans as "did not match" with the reason.
4. Read `IngestConfig`. Both publisher beans are conditional, so a value that matches neither leaves the port with no implementation.
5. Check whether the change was ever tested: the gateway has no `*WiringTest`, while the other eight modules do.

**Fix now vs fix properly.**
- Now: set the value to `kafka` (or remove the property, since Kafka is the default per ADR-0012) and redeploy. A managed Kafka service is still the `kafka` backbone; only the bootstrap servers change.
- Properly: bind the property as an enum in a validated `@ConfigurationProperties`, so a bad value fails with a message that lists the allowed values. Add a gateway wiring test that assembles the context with each allowed value and with a bad one. Validate configuration in CI before it reaches a pod.

**How you'd test it.** The sink writer's `SinkWiringTest` is the pattern to copy: a `@SpringBootTest` that assembles the context with no Docker, because the listener containers do not auto-start and connections are lazy. For the gateway I would add the same with `streampulse.backbone` set to `kafka`, `kinesis`, absent, and a bad value, asserting the first three assemble and the last fails clearly. That test does not exist for the gateway, so it is **[K]**.

**Spoken answer (60-90 seconds).**
I would read the first failure block and not the stack trace: it says an event publisher bean could not be found for the use case. In my gateway the composition root declares two publisher beans selected by a property, one for Kinesis and one for Kafka, and the Kafka one is also the default when the property is missing. Missing is the key word: the customer set the property to a value that is neither, so both conditions fail and the port has no implementation. Spring refuses to start, which is what I want, because a missing dependency should fail at startup and not at the first request. The fix now is to set the value to kafka, since a managed Kafka service is still Kafka. The fix properly is to bind the value as an enum with validation so the error says what is allowed, and to add a wiring test for the gateway. The other services have one, and the gateway does not. I would say that gap openly.

**Follow-ups the interviewer will ask.**
- *Why wire the use case by hand instead of `@Service`?* A plain `new` in a unit test, and one reviewable composition root. A transactional class needs a Spring-managed proxy, which is why the control plane differs.
- *Why a property and not a profile?* A profile cannot say "Kafka unless told otherwise" without a negation on the other side.
- *Constructor injection only: why?* The class cannot be built half-wired, and a circular dependency fails at startup.

**Tie to your code.** [L] [`IngestConfig.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/config/IngestConfig.java), [`SinkWiringTest.java`](../../../../../streampulse/services/sink-writer/src/test/java/com/streampulse/sink/config/SinkWiringTest.java) (the pattern), [`application.yml`](../../../../../streampulse/services/ingest-gateway/src/main/resources/application.yml). A gateway wiring test and an enum-bound property are **[K]**.

---

## Scenario 2 🟢 The customer's client does not split oversized batches because the docs promised a 413

**Situation.** Tuesday 13:30, a customer integrates against our OpenAPI document (example). Their client was written to split a batch and retry when it receives a 413. In production a batch of 600 events gets a 400 with `application/problem+json`, which their client treats as a permanent client bug and drops the batch (example). Telemetry is lost for about two hours before someone notices (example).

**Level.** 🟢 Beginner.

**What's being tested.** Contract drift between the documented API and the code, how the error shape works, and judgement about which side to change.

**Clarifying questions to ask first.**
1. What exactly does the client send and receive? Capture the request size and the response status and body.
2. Does our OpenAPI document say 413 for this case, and which version is published to the customer?
3. How does the customer's client classify 4xx versus 5xx?
4. Is there more than one client that depends on this behaviour?
5. Does a contract test check every documented response, or only some?

**Flow of control and data.**

```
POST /v1/events:batch (600 events)
   └─▶ @Valid @RequestBody EventBatchRequest ─▶ @Size(max = 500) on events ─▶ MethodArgumentNotValidException
   └─▶ IngestExceptionHandler.handleValidation ─▶ 400 problem+json "Validation failed" (message names the field)
OpenAPI ingest-v1.yaml documents '413' "Batch exceeds 500 events"  ─▶ the code never returns it
properties: max-batch-size is bound and validated but never read; the DTO hard-codes 500
```

**Diagnosis steps.**
1. Reproduce with 501 events against a local gateway and read the status and the body. My end-to-end test does the same and asserts a 400 whose body contains `at most 500 events`.
2. Read the OpenAPI response list for the endpoint and compare it with the exception handler's mappings.
3. Search for readers of `maxBatchSize`: it is bound in `IngestProperties` and I found no reader in main code.
4. Look at the contract test: it asserts only that the 202, 400 and 429 responses exist, so it cannot catch a documented 413 that is never returned.
5. Check the published spec version the customer holds, and whether it was ever different.

**Fix now vs fix properly.**
- Now: tell the customer the actual behaviour and the limit (500 events per batch), and ask them to split client-side before sending, treating any 400 as non-retryable. Help them recover the lost window from their own buffers if they kept them.
- Properly: decide the contract with the customer, because both directions are a change for someone. Returning 413 matches the published spec, but 413 usually means a payload too large in bytes. Changing the spec to say 400 is truthful, and it breaks clients written to the spec. Whichever is chosen, a contract test must cover every documented status, the DTO limit and the property must come from one source, and the change needs a version note.

**How you'd test it.** A contract test that sends 501 events and asserts the documented status and problem type. A check that the OpenAPI response list and the handler mappings agree. The existing end-to-end test pins the current 400, so changing the behaviour changes that test deliberately.

**Spoken answer (60-90 seconds).**
I would reproduce it first, with 501 events and look at the real status and body. My end-to-end test already pins a 400 with a problem json body that says at most 500 events, while my OpenAPI document lists a 413 for the same case. So the document and the behaviour disagree, and the customer coded to the document. I would also look at why nobody caught it: my contract test only asserts that 202, 400 and 429 exist, so a documented response that is never returned passes. In the room I would not change the API unilaterally. I would tell the customer the real behaviour and the 500 limit so they can split their batches, then decide with them which side moves, since returning 413 follows the spec but changes the status for current clients, and changing the spec is truthful but breaks anyone who followed it. Either way I would add a contract test that checks every documented status, and make the limit come from one place, because today the property is bound and never read.

**Follow-ups the interviewer will ask.**
- *Is 400 wrong?* It is a defensible choice for a validation failure, and the error is machine readable. The defect is that the document says otherwise.
- *Why problem+json?* One error shape for clients to parse; RFC 7807 is the standard media type for it.
- *Why did quota use 429 and saturation 503?* The tenant's own limit versus our capacity; a client reacts differently, and both carry `Retry-After`.

**Tie to your code.** [L] [`ingest-v1.yaml`](../../../../../streampulse/api/openapi/ingest-v1.yaml) (the documented 413), [`IngestDtos.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestDtos.java) (`@Size(max = 500)`), [`IngestExceptionHandler.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestExceptionHandler.java), [`IngestEndToEndIT.java`](../../../../../streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/adapter/IngestEndToEndIT.java) (pins the 400; I did not run it today). The contract test that checks every status is **[K]**.

---

## Scenario 3 🟡 Consumer lag on the aggregates topic keeps growing

**Situation.** Wednesday 17:20, the customer's dashboard shows aggregate freshness slipping from about 5 s to several minutes (example). `kafka-consumer-groups` shows group `sink-writer` with a total lag of 480,000 and rising by about 3,000 a second (example). Nobody has paged because the service is "up".

**Level.** 🟡 Intermediate.

**What's being tested.** Telling apart three different causes of lag (store outage, slow store, poison record), reading consumer-group output, and knowing which behaviours are by design.

**Clarifying questions to ask first.**
1. Is the lag on all partitions or on one? Is the committed offset moving at all?
2. Did anything change: a deploy, a Postgres change, a schema change, a traffic increase?
3. What do the sink's flush metrics and logs say: failures, dead letters, refusing-to-skip messages?
4. Is Postgres healthy: connections, locks, slow upserts?
5. Is the group rebalancing repeatedly?

**Flow of control and data.**

```
telemetry.agg.v1 (6 partitions) ─▶ @KafkaListener batch (concurrency 3: 2 partitions per thread), manual ack, read_committed
   ─▶ decode: undecodable ─▶ dead-letter     valid ─▶ BatchWriter.submit (bounded queue 2,000, offer timeout 1 s)
   ─▶ flusher: 200 rows or 100 ms ─▶ Postgres upsert (INSERT ... ON CONFLICT DO UPDATE)
   ─▶ awaitAll(poll budget 30 s) ─▶ ack.acknowledge()   (offset commits only AFTER the durable write)
failure: flush retries ─▶ isolate record by record ─▶ some succeed ─▶ the failures are poison ─▶ dead-letter
         none succeed ─▶ cannot tell a bad record from a dead store ─▶ fail all ─▶ listener redelivers
error handler: never skips, never gives up, capped exponential backoff
```

**Diagnosis steps.**
1. Run `kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group sink-writer`. Compare `CURRENT-OFFSET` and `LAG` per partition. A frozen current offset with growing lag means a stuck consumer; a moving offset means it is just too slow.
2. Read the sink metrics: `streampulse.sink.batch.flush` (duration), `streampulse.sink.batch.flush.failures`, `streampulse.sink.dead.letters` and the `streampulse.sink.batch.queue.depth` gauge. A queue pinned near 2,000 means the writer is the bottleneck. Prometheus may rewrite the dots as underscores.
3. Search the logs for `refusing to skip <topic>-<partition>@<offset>` repeating on one offset. That is the error handler refusing to skip, which means one batch is being redelivered forever.
4. Check Postgres for an outage or slow upserts. An outage makes lag grow by design: the handler waits it out and nothing is lost.
5. Look for consumer poll timeouts and rebalances in the logs (verify the exact message). `max.poll.interval.ms` is 300,000 and must exceed the poll budget plus the longest backoff.
6. Remember `read_committed`: the consumer cannot read past the last stable offset, so an open upstream transaction looks like lag with no new records.

**Fix now vs fix properly.**
- Now: if it is a Postgres outage, fix Postgres and watch the lag drain; the design promised no loss. If one partition is stuck on one offset, a single poison record alone in a batch looks like an outage, so park that record in the dead-letter topic by hand and move the group past it with the group stopped (an operational action to agree with the customer first). If it is throughput, check Postgres first.
- Properly: alert on lag growth rate per partition and on the freshness timer, not on "service is up". Give a failing single-record batch a bounded number of attempts when a store health probe says the store is up, so one poison record cannot block a partition. Load-test the sink: the repo's notes say it was never killed and I have no throughput measurement for it. Note that with 6 partitions, more than 6 consumers in the group adds nothing.

**How you'd test it.** `BatchWriterTest` covers the writer. `PoisonRecordIT` and `NoLossNoDoubleCountIT` exist, but I did not run them today, and their failures are injected exceptions, not killed processes. The single-poison-alone case, and a stuck partition alarm, are **[K]**.

**Spoken answer (60-90 seconds).**
I would first get the consumer-group description and look at the offsets per partition, because the three causes look different. If one partition is frozen at one offset and my logs repeat refusing to skip that offset, a single poison record is in a batch by itself. My writer retries the batch, then tries records one at a time, and if none succeed it cannot tell a bad record from a dead store, so it fails them all and waits. If every partition's offset is frozen and flush failures are rising, Postgres is down, and the lag is my design working: the offset commits only after the durable write, and the error handler never skips. If offsets move but the queue depth sits near its limit, the writer is slow. I would not scale first. I would fix the cause, then add alerts on lag growth and freshness. I should say honestly that I have no throughput number for the sink and never killed it in testing.

**Follow-ups the interviewer will ask.**
- *Why commit after the write and never skip?* Losing a record is unrecoverable and a delay is recoverable; ADR-0013 records the choice.
- *Why a manual ack?* The offset must move only after the write is durable, so a crash redelivers and the upsert makes that safe.
- *What is the risk of a very long backoff?* The consumer must not exceed `max.poll.interval.ms`, or the broker evicts it mid-outage and the group rebalances.

**Tie to your code.** [L] [`AggregateBatchListener.java`](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/adapter/in/kafka/AggregateBatchListener.java), [`BatchWriter.java`](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java) (`isolate`), [`SinkConfig.java`](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/config/SinkConfig.java) (never-give-up handler), [`application.yml`](../../../../../streampulse/services/sink-writer/src/main/resources/application.yml), [`PoisonRecordIT.java`](../../../../../streampulse/services/sink-writer/src/test/java/com/streampulse/sink/adapter/in/kafka/PoisonRecordIT.java).

---

## Scenario 4 🟡 The gateway sheds 503s at a plateau while CPU is low; is it virtual-thread pinning?

**Situation.** Thursday 10:00, a customer load test (example). Past about 45,000 events a second the gateway starts returning 503, p99 climbs, and CPU on the gateway is around 40% (example). A customer engineer read that virtual threads can pin carrier threads and declares that this is the cause. The repo's own saturation run, from the repo's notes, was clean at 40,000 events a second and shed 503s from 45,000 (11.8% errors at that step), on one laptop with the load generator sharing the CPU.

**Level.** 🟡 Intermediate.

**What's being tested.** Separating hypotheses before naming a cause, what pinning is and how to detect it, and honesty about what my own measurements prove.

**Clarifying questions to ask first.**
1. What does the 503 body say: the capacity rejection, or the publisher-unavailable one?
2. What do the rejection counters and the circuit breaker state say?
3. Which JDK is the service running, and is the property for virtual threads on?
4. Do any libraries on the request path use `synchronized` around blocking calls?
5. Was the load generator able to hold its offered rate, or did it slow itself down?

**Flow of control and data.**

```
request on a virtual thread ─▶ quota check (Redis) ─▶ Semaphore.tryAcquire (64 permits, 250 ms wait)
   not acquired ─▶ BackpressureException ─▶ 503 + Retry-After   (designed shedding)
   acquired ─▶ idempotency claim (Redis) ─▶ publishAndWait: breaker ─▶ timeout ─▶ Kafka producer ─▶ ack
        breaker open ─▶ PublishUnavailableException ─▶ 503 as well (a different cause)
pinning (JDK 21): a virtual thread blocked inside synchronized (or native code) keeps its carrier occupied
```

**Diagnosis steps.**
1. Read the 503 response body and log line. The two 503 mechanisms use different problem types. The repo's own notes say I never saw the body in my saturation run, so the cause there was found by elimination, not observed.
2. Read the counters: `streampulse.ingest.events.rejected` (capacity), `streampulse.ingest.publish.failures`, `streampulse.ingest.idempotency.unavailable`, and the breaker state. A rising capacity-rejection counter with a healthy breaker points at the 64-permit bound.
3. Add or read a gauge for permits in use. I do not have one; my notes list it as a task.
4. Test pinning directly. On JDK 21 start the service with `-Djdk.tracePinnedThreads=full` and look for stack traces, or record JFR and look for pinned-virtual-thread events (verify both names and behaviour in the docs for your JDK).
5. Compare CPU with carrier thread state in a thread dump (`jcmd <pid> Thread.dump_to_file`, verify the format option for JDK 21). Busy-but-low-CPU with all carriers blocked is the pinning signature; high CPU is just CPU.
6. Search main sources for `synchronized`. My grep finds it in main code only in the alert engine's `AbsenceSweeper` and `RuleBookLoader` lifecycle methods, as short critical sections and not around blocking I/O, by my reading. Pinning would more likely come from a dependency.

**Fix now vs fix properly.**
- Now: if the capacity counter is rising with a healthy breaker, this is the bound doing its job. Scale out, or raise permits cautiously and watch the publish path. Do not conclude "pinning" without a trace.
- Properly: run the measurement my ADR promised and never did (`jdk.tracePinnedThreads`, flame graphs), add the permit gauge and a 503-type log line, and repeat the saturation run with finer steps. If a dependency pins, upgrade it or move that call off virtual threads. A newer JDK is reported to remove most `synchronized` pinning (JEP 491, which I believe lands in JDK 24); verify the JDK before relying on it. My ADR states that same VERIFY.

**How you'd test it.** A load run with a client that holds the offered rate and reports 429 and 503 separately (my load tooling has that switch, and a test pins it). A JFR or trace-pinned run is the missing evidence. Unit tests for the semaphore and backpressure exist in `IngestServiceTest`, which includes a 200-iteration race test, but they do not measure carriers.

**Spoken answer (60-90 seconds).**
I would not accept pinning as the answer yet, because there are two different 503s in my gateway and I need to know which one fired. One is my own backpressure: a fair semaphore of 64 in-flight batches with a 250 millisecond wait, then 503 with Retry-After. That is designed shedding. The other is the circuit breaker being open. I would read the response type and the counters first. Pinning is a real Java 21 issue, where a virtual thread blocked inside a synchronized block holds its carrier thread, and I prefer reentrant locks around blocking calls for that reason. But my honest position is that I have not measured it: my ADR says to run with the trace-pinned-threads option and I never did, and my own saturation result at 45,000 events a second was explained by elimination, not by observation. So I would add a permit gauge, log the 503 type, run the trace, and only then decide. I would also say my numbers come from one laptop with the load generator on the same machine.

**Follow-ups the interviewer will ask.**
- *What is a virtual thread?* A lightweight JVM-scheduled thread that unmounts from its carrier when it blocks on I/O, final in Java 21. I enable it in the gateway, alert engine and activity feed only, not in the sink writer or stream processor.
- *Why a fair semaphore?* Permits go in arrival order, so a request cannot be starved into an unexplained long tail.
- *Why block on the publish at all?* A 202 promises durability, so the response must wait for the broker acknowledgement; on a virtual thread that wait is cheap.

**Tie to your code.** [L] [`IngestService.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java), [`ADR-0006`](../../../../../streampulse/docs/adr/0006-virtual-threads-over-webflux.md), [`06-numbers.md`](../../../../../streampulse/docs/interview/06-numbers.md) (measured rows and conditions), [`IngestServiceTest.java`](../../../../../streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/application/IngestServiceTest.java). The pinning measurement is **[K]**: not done.

---

## Scenario 5 🔴 A schema change deployed producer-first breaks the stream processor

**Situation.** Friday 15:00 (example). The customer's team, extending our pipeline, adds an optional field with a default to the telemetry event schema and deploys the producer first (example). The build-time compatibility check was green. Within minutes the `telemetry.raw.v1.dlt` topic starts filling and the aggregates for the customer's tenant undercount (example). Rolling the producer back stops new dead letters.

**Level.** 🔴 Senior.

**What's being tested.** What a BACKWARD compatibility gate proves and what it does not, raw Avro without a registry, deploy ordering, and recovery when the late events have already missed their window.

**Clarifying questions to ask first.**
1. Which service was deployed first, and what is the schema diff (field added, where, with what default)?
2. What reason do the dead-letter records carry, and is it the same for all of them?
3. Are the dead-lettered bytes preserved, and for how long is the raw topic retained?
4. Are there other consumers of the topic (archive, other teams)?
5. Is the processor's window state affected, or only the decode?

**Flow of control and data.**

```
producer v2 (new field) ─▶ AvroBinaryCodec: raw Avro binary, no schema id, no field names on the wire
   ─▶ telemetry.raw.v1 ─▶ processor v1 (old generated class is writer AND reader schema)
         decode fails or misparses ─▶ Decoded.Rejected ─▶ dead-letter topic with original bytes + reason header
         a misparse that still decodes would NOT be dead-lettered
gate: SchemaCompatibilityTest = BACKWARD (new reader reads old data): says consumers deploy FIRST; nothing enforces the order
```

**Diagnosis steps.**
1. Read the reason header on the dead-lettered records (for example with `kafka-console-consumer.sh --topic telemetry.raw.v1.dlt --from-beginning --property print.headers=true`, verify the flags for your Kafka version). A decode error pointing at trailing bytes or a bad read confirms a version mismatch.
2. Build the timeline: deployment times of producer and processor against the first dead letter.
3. Diff the producer's and the processor's `TelemetryEvent` schema. My codec builds both writer and reader from the same generated class, and its javadoc says it does not resolve evolution across versions.
4. Check for silent misparse: compare event counts for a window against the producer's own count. A field added in the middle can shift later fields and decode without error. I have not run a mixed-version test, so I cannot say which happens for a given change.
5. Check whether the dead-lettered events can be replayed: the DLT keeps the original bytes, and the raw topic retains seven days.

**Fix now vs fix properly.**
- Now: roll the producer back, which stops the loss. Deploy the new consumer version first, then the producer. Do not replay blindly: the aggregates use 10 s windows with a 5 s grace, so events replayed hours later are far past the grace and would be dropped as expired-window records by my reading of the config. A recovery needs a backfill path, which I have not built.
- Properly: make the order enforceable. Either add Schema Registry style framing so the writer schema travels with each record, or give the codec an explicit writer schema and a version header. For breaking changes use a new topic version (`telemetry.raw.v2`) with dual-write, as ADR-0005 describes. Add a mixed-version integration test. Alert on the DLT rate. Enforce consumers-first in the deploy pipeline.

**How you'd test it.** `SchemaCompatibilityTest` proves three breaking fixtures are rejected and an optional field with a default passes. That is the build-time half. The runtime half, an old processor reading new bytes and the reverse, is **[K]**: I never ran a mixed-version test. A related state-store check exists: `WindowAccumulatorSerde` writes a format-version byte and refuses to read a version it does not know, which fails loudly, but it has no migration for an older layout.

**Spoken answer (60-90 seconds).**
I would start with the dead letters, because they preserve the original bytes and a reason. Then I would build the timeline: which service deployed first. My compatibility gate is BACKWARD, which means a new reader can read old data, so the rule is that consumers deploy first, and nothing in my pipeline enforces it. At runtime my codec uses the same generated class as both writer and reader schema, so it does not resolve versions. Avro binary carries no field names, so an old consumer reading new bytes can fail to decode, which lands in the dead-letter topic, or in the worst case misparse without an error. I have not tested a mixed-version rollout, so I would say I cannot size that second risk. The fix now is rollback and consumers first. Replaying is not simple, because the events are far outside my five second grace and would be dropped. The proper fix is a registry or a version header, topic versioning for breaking changes, and a mixed-version test in CI.

**Follow-ups the interviewer will ask.**
- *Is BACKWARD enough?* It protects the build against a bad schema; it does not protect a rolling deploy. Deploy order and runtime schema resolution are separate controls.
- *Why raw Avro without a registry?* Smaller and simpler; a heartbeat was 134 bytes against about 409 as JSON (from the repo's notes, one measurement). The cost is exactly this gap.
- *What about a Java record change in the state store?* The serde's version byte makes an unknown layout fail at restore, not silently; a real migration would read the old version and write the new, with a golden-bytes test.

**Tie to your code.** [L] [`AvroBinaryCodec.java`](../../../../../streampulse/libs/contracts/src/main/java/com/streampulse/contracts/codec/AvroBinaryCodec.java), [`SchemaCompatibilityTest.java`](../../../../../streampulse/libs/contracts/src/test/java/com/streampulse/contracts/SchemaCompatibilityTest.java), [`ADR-0005`](../../../../../streampulse/docs/adr/0005-topic-and-schema-versioning.md), [`WindowAccumulatorSerde.java`](../../../../../streampulse/services/stream-processor/src/main/java/com/streampulse/processor/adapter/streams/WindowAccumulatorSerde.java). The mixed-version test and a registry are **[K]**.

---

## Scenario 6 🔴 After the processor pod restarts, the dashboard undercounts and nothing alerts

**Situation.** Saturday 04:40 (example). The stream processor pod was killed and came back after a 45 s outage (example). Afterwards the customer sees closed windows with lower counts than their own producer-side totals, with no duplicates. Nothing in the service's own metrics changed. The processor's log is full of `Skipping record for expired window` warnings.

**Level.** 🔴 Senior.

**What's being tested.** The difference between exactly-once on topics and correctness of event-time logic, how a restart backlog interacts with a grace period, observability gaps, and the cost of each fix. This is a failure I measured in my own system and did not fix.

**Clarifying questions to ask first.**
1. How long was the outage and how big was the backlog afterwards?
2. How many partitions feed one aggregate key? Raw topic is keyed by session, so one aggregate's events come from many partitions.
3. Is the loss the same count as the processor's own dropped-record counter and warning count?
4. What are the window and grace settings (10 s window, 5 s grace)?
5. Which guarantee did the customer assume, and which did we state?

**Flow of control and data.**

```
raw topic (12 partitions, keyed by sessionId) ─▶ decode/validate ─▶ de-dup by event id ─▶ re-key by tenant/title/region
   ─▶ 10 s window, 5 s grace ─▶ aggregate (WindowAccumulator) ─▶ suppress(untilWindowCloses) ─▶ aggregates topic
processing.guarantee = exactly_once_v2: output + changelog + offsets in one transaction (no duplicates)
after a restart: the backlog is read from many partitions in an arbitrary order
   ─▶ later events reach the window first ─▶ stream time jumps past windows that still have on-time events
   ─▶ the 5 s grace treats the earlier events as late ─▶ "Skipping record for expired window" ─▶ dropped
```

**Diagnosis steps.**
1. Count the `Skipping record for expired window` warnings and compare with the missing events. In my own test the two matched exactly, and the task-level dropped-records metric agreed.
2. Check the Kafka Streams dropped-records metric. The service's own `streampulse_processor_*` metrics do not show this loss, which is the observability gap.
3. Compare the outage length and the backlog size with the window size and grace. A grace of 5 s cannot absorb a 45 s backlog replayed out of order.
4. Rule out your own test: my notes record re-running with the closing event sent long after recovery, and the loss was the same.
5. Confirm there are no duplicates, which separates this from the exactly-once question.

**Fix now vs fix properly.**
- Now: tell the customer which windows are affected and that totals for those windows are lower bounds. Recompute them from a source of truth if one exists (the archive path, or the producer's own counts).
- Properly: every fix changes a documented guarantee and needs an ADR. A larger grace makes every window slower by the same amount. Emitting revised windows gives up the one-final-answer contract. Holding stream time back until the backlog drains is an architectural change; I have not verified whether `max.task.idle.ms` helps. Add a late-drop counter so the loss is visible in service metrics.
- The mechanism is likely but not proven, and it is unfixed in my repo.

**How you'd test it.** The crash was done by a script (`kill -9` of the processor), not by a JUnit test, and `StreamProcessorIT` does not kill anything. `TelemetryTopologyTest` uses `TopologyTestDriver`, which cannot prove rebalancing, real transactions under exactly-once, broker failure or offset commits. A repeatable test that kills the processor and compares closed windows with the sent counts is the missing piece. I also did not test a graceful SIGTERM, a short outage or a second instance taking over.

**Spoken answer (60-90 seconds).**
I would say plainly that this is a failure I reproduced in my own system and did not fix. After a kill of the processor and a 40 to 50 second outage, roughly a third of the on-time events (1,482 of 4,000 and 2,554 of 8,000 in two runs) were dropped as expired-window records, with no duplicates, and the count of drops matched my processor's warning count. Exactly-once is a statement about topics and offsets. It says nothing about whether event-time logic sees events in an order its grace period can absorb. My raw topic is keyed by session, so one aggregate's events come from many partitions, and after a restart the backlog arrives out of order, stream time jumps ahead, and a five second grace calls earlier events late. The mechanism is likely and not proven, and my service metrics did not show it. Each fix changes a guarantee: a bigger grace slows every window, revisions give up one final answer, and holding stream time back is architectural. So I would tell the customer which windows are affected, add a late-drop metric, and write the ADR before changing anything. These numbers are from one laptop, one broker, one instance.

**Follow-ups the interviewer will ask.**
- *Why did the aggregates not duplicate?* The de-duplicator and the transactional output mean a replay does not double count; the problem is dropped, not repeated.
- *Would suppress change this?* Suppress emits one final record per window when it closes, so a window that closed before the late events arrived cannot take them. It also holds a quiet partition's last window open; the buffer is unbounded in my config, which I have not measured.
- *What about the gateway when it is hard-killed?* By my reading of `IngestService`, the idempotency claim is made before the publish and is released only by an in-process failure path, so a hard kill between the claim and the broker ack could leave a claimed id with no event, and a client retry would then be treated as a duplicate. I have not tested it. It is a question to answer before claiming no loss.

**Tie to your code.** [L] [`TelemetryTopology.java`](../../../../../streampulse/services/stream-processor/src/main/java/com/streampulse/processor/adapter/streams/TelemetryTopology.java) (window, grace, suppress), [`05-what-broke.md`](../../../../../streampulse/docs/interview/05-what-broke.md) (the measured failure and its limits), [`deep-dive.md`](../../../../../streampulse/docs/deep-dive.md), [`IngestService.java`](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java) (claim then publish). A fix and an automated kill test are **[K]**.
