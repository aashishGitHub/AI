# Module 13 (simple) — Java backend (Spring, Kafka, testing) via streampulse

> **Read this first**
> - **What it is for:** the Java 21 backend I built in `streampulse`. Modules, domain types, Spring, Kafka, reliability, tests, concurrency.
> - **Who it is for:** a beginner. Each term is explained the first time it appears.
> - **Full version:** [13-java-backend-streampulse.md](../13-java-backend-streampulse.md) has the real code snippets and the harder follow-ups.

Lane tags: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only.

- Everything built here is **[L]**. The code is in a **sibling repo**, `streampulse`, next to this one. Links below work only if it is checked out beside `AI`.
- Some commits are co-authored with Claude. So I must defend every line, including lines that contradict my own conventions. This guide names several.
- The build is **Gradle with the Kotlin DSL**, not Maven.
- On 2026-10-20 I ran one Gradle invocation offline: `:libs:platform:test`, `:libs:contracts:test`, and `:services:ingest-gateway:test` filtered to `IngestServiceTest` and `IngestArchitectureRulesTest`. Result: 55 passed, 0 failed, `BUILD SUCCESSFUL in 30s`.
- I did **not** run any Testcontainers `*IT` class. Every statement about an integration test comes from reading its source.
- Numbers are labelled by origin: config, the repo's own docs (one developer machine), derived by counting, or my own small programs in a scratch directory.
- Delivery semantics, the Redis claim, the outbox and Debezium are explained in [04-event-driven-reliability.md](../04-event-driven-reliability.md). Phase 5 here shows only the Java mechanics.

---

## Phase 1 — Project structure and architecture rules (modules, hexagonal packages, dependency direction enforced by tests)

**Analogy: a city with building codes that inspectors check by machine.** Districts (modules) have fixed roads between them. The code says "houses may not connect straight to the power plant". An automatic inspector checks it on every change.

### How the repo is organised
- It is one Gradle build with twelve included projects: two libraries, eight services, one function and a load generator.
- `libs:platform` holds value objects every service shares, such as `TenantId` and `EventId`.
- `libs:contracts` holds the Avro schemas, generated classes and the codec.
- Each service depends on both libraries. A service is a **leaf**: nothing else compiles against it. I checked the build files. No service depends on another service.
- Why split: producers and consumers must code against the same contract, without one service's jar dragging in another's internals.
- Shared build behaviour lives in **convention plugins** (reusable build setup) in an included `build-logic` build. A service opts in with one `id("streampulse.spring-service")` line. That pins the Java 21 toolchain, compiler lint flags, JUnit, ArchUnit and actuator once.
- Settings file: [settings.gradle.kts](../../../../../streampulse/settings.gradle.kts).

### Hexagonal architecture in one minute
- **Hexagonal** (also called ports and adapters) puts the business rules in the middle and the outside world around the edge.
- Each service has:
  - `domain`: rules and **ports** (interfaces the domain owns);
  - `application`: use cases;
  - `adapter.in`: things that call me, such as REST controllers and Kafka listeners;
  - `adapter.out`: things I call, such as Kafka, Redis and JDBC;
  - `config`: wiring.
- Dependencies point inward. The domain declares an interface like `EventPublisher`. An adapter implements it.
- Benefit: I test the use case with plain `new` and a fake. I can swap an adapter, as I did with the Kinesis publisher beside the Kafka one.
- Cost: more files. About 341 main source files across the build, counted by file name.

### Enforcing the dependency direction
- **ArchUnit** reads compiled bytecode and expresses architecture rules as ordinary JUnit tests.
- The rules live in each module's own test directory, not in `libs/platform`. ArchUnit scans the test classpath. `libs/platform` depends on no service, so it cannot see their classes. The ingest test says this in its own header.
- Ingest-gateway rules:
  - domain and application must not touch gRPC, protobuf, servlet or Spring web types;
  - `adapter.in` must not reach `adapter.out`;
  - adapters must not name the `IngestService` class. They use its `IngestUseCase` port.
- Depending on the interface lets a test swap in a recording double, and stops adapters reaching implementation details such as the permit count.
- A cycle rule I wrote and ran once (not in the build) reported 47 classes and no violations. It is a candidate rule that passes today. It is not enforced by the repo.
- Rule file: [IngestArchitectureRulesTest.java](../../../../../streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/IngestArchitectureRulesTest.java).

### Do these rules guard anything, and where are the gaps (senior)
- Honest answer: the rule sets are uneven.
- Counting `@DisplayName` annotations: 51 rule tests across ten files (nine modules plus `libs/platform`).
- Ingest forbids protocol types in the core and adapter shortcuts. But it has no rule that the domain is free of Spring, Kafka or Redis types, and no field-injection rule. Control-plane, activity-feed, alert-engine and sink-writer do have those.
- The **clock rule** (production code must not call `Instant.now()`) exists only in control-plane and mcp-server.
- Ingest-gateway still calls `Instant.now()` in `IngestController` and `AvroEventMapper`, and `System.currentTimeMillis()` in the Redis rate limiter. That contradicts the convention in `CLAUDE.md`.
- In `libs/platform`, the adapter-direction rule uses `allowEmptyShould(true)` and has no `..adapter.in..` classes to check. So it passes vacuously.
- I have not mutated any architecture rule to see it fail. I cannot claim they would catch a regression. That is not measured.

### One shared rules library (senior)
- That is the obvious refactor. I did not build it.
- The rules would become a test-fixtures module that takes a root package. Each service calls it with its own exceptions. That removes the drift.
- I stopped at per-module copies because each phase added the rule protecting what it had just built. The cost is the unevenness.
- I would accept a little less flexibility per service for one place to add a rule. I would add the clock rule and the "domain free of Spring, Kafka, Redis" rule there first.

### Words you'll hear
| Term | Meaning |
|---|---|
| Gradle multi-module | One build containing many projects |
| Convention plugin | Shared build settings applied with one line |
| Hexagonal / ports and adapters | Business rules inside, outside world plugged in through interfaces |
| Port | An interface the domain owns |
| Adapter | Code that implements a port for a real system |
| ArchUnit | A library that tests architecture rules |
| Composition root | The one place that wires everything together |
| Vacuous pass | A rule that passes only because there is nothing to check |

**Say it in one breath:** I split the system into modules and hexagonal packages and make the dependency direction a failing test with ArchUnit, but the rule sets are uneven and I have not mutated a rule to prove it catches anything.

---

## Phase 2 — Domain modelling in modern Java (records, immutability, validation in constructors, value objects)

**Analogy: a passport with a photo you cannot swap.** A plain string is a blank piece of paper anyone can write on. A value object is a passport: issued only if valid, and it cannot be edited afterwards.

### Why `EventId` and `TenantId` are records
- A bare string cannot say what it means. `publish(titleId, tenantId)` compiles with the arguments swapped. With a tenant id, that swap is a data leak.
- A **record** gives a distinct type, an automatic constructor, accessors, `equals`, `hashCode` and `toString`. It is implicitly final and shallowly immutable.
- I put validation in the **compact constructor** (the short constructor form in a record).
- So an `EventId` that exists is always a canonical lowercase UUID. A `TenantId` that exists is always lowercase alphanumerics with internal hyphens.
- Everything downstream can trust the value without re-checking.

### `equals` and `hashCode`, and `HashMap` keys
- Contract: equal objects must return equal hash codes.
- A `HashMap` uses the hash code to pick a bucket, then `equals` to find the entry inside it.
- If I override `equals` and forget `hashCode`, two equal keys can land in different buckets. The map treats them as different keys.
- A record derives both from all its components. So I can use `TenantId` or `AggregateKey` as a map key safely.
- Recent JDKs convert a heavily collided bucket into a tree. I am not certain of the exact thresholds. Verify in current docs before quoting.

### Checked vs unchecked exceptions
- A **checked** exception must be declared or caught. An **unchecked** one extends `RuntimeException` and need not be.
- My validating constructors throw `IllegalArgumentException`. Control-plane domain exceptions like `NotFoundException` and `InvalidInputException` extend `RuntimeException`.
- So service signatures stay clean, and the web layer maps them to status codes in one place.
- It matters with Spring: `@Transactional` rolls back on unchecked exceptions by default, but commits on checked ones.
- I did not take that from docs. `TransactionBehaviourIT` runs against a real Postgres. It asserts a checked failure still commits the row unless `rollbackFor` is set.

### Validation and normalisation in a compact constructor
- The compact constructor runs before the fields are assigned. It is the place to reject bad input and reassign the parameter to its canonical form.
- In `EventId`:
  - require non-null;
  - parse with `UUID.fromString`;
  - compare the round-tripped text with the input, because the JDK parser is lenient about some malformed strings;
  - rethrow with the original cause, so a bad client payload does not look like an internal error;
  - lowercase with `Locale.ROOT`, so the Redis dedup key is stable.
- `TenantId` does the same with a regex and a 32-character limit. It trims and lowercases before validating. So `" StreamFlix "` is accepted and stored as `streamflix`.
- My scratch demo (Java 21): two regions with different spelling are equal, a map holds one entry with count 2, and a batch keeps its two original ids after the source list grows.
- `List.copyOf` in a compact constructor is the same defensive copy that `IngestCommand` makes.
- File: [EventId.java](../../../../../streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java).

### Sealed interfaces and pattern-matching switches
- A **sealed interface** closes the set of subtypes. A `switch` over it needs no `default`. The compiler fails the build when I add a subtype and forget a branch.
- I use it for the result of validating or decoding a record. `Validation` has `Valid` and `Invalid`. The Kafka decoders return a sealed `Decoded` with `Valid` and `Rejected`.
- In the alert engine, `Evaluators` switches over the sealed `Condition`. Its comment says it replaced a registry map for exactly this compile-time reason.
- Java 21 pattern matching for `switch` is final. I use only type patterns. I searched and found no record deconstruction patterns and no `when` guards in main code.
- The first removes a registry that could silently miss a case. The second is the algebraic result type (a small set of named outcomes) that lets a topology branch without exceptions for control flow.

### Where the domain model falls short (senior)
- **Gap 1: the telemetry payload is dropped.**
  - The Avro schema defines six typed payload variants. `IngestEvent.payload` is an `Object`.
  - `AvroEventMapper` calls `setPayload(null)` with a comment that variants land later.
  - So the processor computes only distinct sessions and the error ratio from the event type. Nothing is payload-driven.
- **Gap 2: `WindowAccumulator` copies its session set on every event.**
  - It is immutable, so that is O(sessions) per update.
  - Its own comment says a sketch such as HyperLogLog would replace it at scale.
  - I have not measured the cost. It is a stated trade, not a number.
- **Gap 3: tenant validation happens in several places on purpose.**
  - The controller via `TenantResolver`, `EventValidator` in the processor, and `AggregateKey.of`.
  - A malformed id from any producer is rejected, at the price of repeating the check on every hop.
- Boundary: value objects protect the **shape** of an id, not its authorization. The tenant still comes from the verified JWT claim.

### Why `IngestCommand` takes `tenantId` as a separate argument (senior)
- The tenant must come from the verified token, never from the request body.
- A separate constructor argument means the wire format cannot supply it, even by accident. The DTO has no tenant field at all, so there is nothing to mistrust.
- The record copies the event list with `List.copyOf`. That rejects null elements and freezes the batch after validation.
- Trade-off: one more parameter at every construction site. I accept it, because a cross-tenant write is the worst failure this system can have.
- File: [IngestCommand.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/domain/IngestCommand.java).

### Words you'll hear
| Term | Meaning |
|---|---|
| Record | A Java class for immutable data with auto-generated methods |
| Compact constructor | The short constructor form where you validate and normalise |
| Value object | A small type that is valid by construction |
| `equals` / `hashCode` | Rules for comparing objects and placing them in hash maps |
| Checked exception | Must be declared or caught |
| Sealed interface | An interface with a closed list of implementations |
| Defensive copy | Copy input so the caller cannot change it later |
| `Locale.ROOT` | A fixed locale so lowercasing is the same everywhere |
| JWT | A signed token that carries identity claims |

**Say it in one breath:** I use records with validating constructors and sealed result types so an invalid value cannot exist, and the tenant always comes from the verified token and never from the request body.

---

## Phase 3 — Spring service design (ports and adapters, configuration, REST/OpenAPI contracts, error handling)

**Analogy: a restaurant with a pass window.** Waiters (controllers) take orders and hand tickets to the kitchen through a fixed window (the port). The waiter does not cook. The head chef (config) decides which kitchen station fills each ticket.

### Dependency injection and constructor injection
- **Dependency injection** means a class receives the collaborators it needs instead of creating them. So I can hand it a fake in a test.
- With constructor injection the dependencies are `final` fields. The class cannot be built half-wired. A circular dependency fails at startup instead of at first call.
- Field injection hides the dependency list. It needs reflection or a Spring context to test.
- That is why `CLAUDE.md` says constructor injection only. Several services have an ArchUnit rule against `@Autowired` fields.
- Test classes do use `@Autowired` fields. That is allowed, because the rules scan production classes only.

### Why ports are interfaces, not abstract classes
- An interface describes a capability with no state. A class can implement many. An abstract class gives one inheritance slot and can carry state I do not want in a port.
- `EventPublisher`, `IdempotencyStore` and `RateLimiter` are interfaces the domain owns. Kafka, Redis and Kinesis adapters implement them.
- Java 8 added default methods to interfaces. I keep ports pure, so a test double is a few lines.
- `RateLimiter` does expose a static `allowAll()` that unit tests use. A small convenience I accepted.

### From HTTP request to Kafka record
- The controller takes the validated body and the `Authentication`. It asks `TenantResolver` for the tenant from the verified JWT.
- It maps DTOs to a domain `IngestCommand`, calls the `IngestUseCase` port, and returns 202.
- The use case:
  - checks the quota first;
  - acquires a permit from a fair `Semaphore` (a counter limiting in-flight work);
  - claims event ids in Redis;
  - publishes through the `EventPublisher` port;
  - waits for the broker acknowledgement.
- `IngestConfig` is the only place that knows which publisher is behind the port. A property selects Kafka (the default) or the Kinesis adapter. Either is wrapped in the same `ResilientEventPublisher` decorator.
- The controller has no business logic by design. So a parity test can assert that gRPC and REST produce the same Kafka records.
- Spring Security validates signature, issuer and expiry before the controller runs. An optional `Idempotency-Key` header lets a client short-circuit a whole retried batch.
- File: [IngestController.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestController.java).

### Error handling in the REST layer
- One `@RestControllerAdvice` per service turns exceptions into **RFC 7807** `application/problem+json`. A client parses one error shape.
- Gateway mapping:
  - `BackpressureException` to 503 with `Retry-After`;
  - `QuotaExceededException` to 429 with `Retry-After`;
  - `PublishUnavailableException` to 503;
  - bean-validation failures and `IllegalArgumentException` to 400;
  - `IllegalStateException` to 500 with a deliberately generic detail.
- Control plane: not found to 404; already exists and conflict to 409; a rule violation to 422; invalid input to 400; an optimistic-lock failure to 409.
- Log backpressure at debug and an unexpected failure at error. Designed rejection must not page anyone.
- The 429 versus 503 split: a quota breach is the tenant's problem. A saturated gateway is mine. A client reacts differently to each.
- File: [IngestExceptionHandler.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestExceptionHandler.java).

### Hand wiring vs `@Service`, and where the design is inconsistent (senior)
- I wired `IngestService`, `KafkaEventPublisher` and `RedisIdempotencyStore` explicitly in `IngestConfig`. So each can be built with plain `new` in a unit test.
- `IngestServiceTest` runs the whole idempotency and backpressure suite, including a 200-iteration race test, without starting Spring.
- Trade-off: one large config class.
- The control plane does the opposite. Its services carry `@Service` and `@Transactional`. A transaction needs a Spring-managed proxy, and the outbox rule depends on it.
- Real inconsistencies:
  - `IngestDrainLifecycle` is annotated `@Component` and also built by an `@Bean` method of the same name with a cast to `(IngestService)`. I believe the `@Bean` definition silently replaces the scanned one. Verify in current docs. The clean fix is to delete the annotation.
  - The property `streampulse.ingest.max-batch-size` is bound and validated but never read. The DTO hard-codes `@Size(max = 500)`.
  - The OpenAPI document lists a 413 for an oversized batch. The code and `IngestEndToEndIT` return 400. The contract and behaviour disagree.
- I ran the unit tests and they passed. But the contract test only asserts 202, 400 and 429 exist, so it cannot catch that mismatch.
- OpenAPI file: [ingest-v1.yaml](../../../../../streampulse/api/openapi/ingest-v1.yaml).

### Is hand wiring just reimplementing Spring (senior)
- I lose component-scanning convenience. I gain testability and a single reviewable composition root.
- I also lose automatic detection of a missing bean until startup. The `*WiringTest` classes that most services have partly cover that. I did not read them closely, and the gateway has none.
- Boundary: this works for classes with no need for proxies. As soon as I need `@Transactional` or `@Cacheable`, the class must be a Spring bean. That is why control-plane differs.
- A decorator such as `ResilientEventPublisher` is deliberate. An annotation-based circuit breaker would need a proxy. It would not apply to a class built with `new`.

### Words you'll hear
| Term | Meaning |
|---|---|
| Dependency injection | A class is given its collaborators, not creating them |
| Constructor injection | Dependencies passed through the constructor |
| Controller | Code that handles an HTTP request |
| Use case | One business operation in the application layer |
| DTO | A plain object that carries data over the wire |
| RFC 7807 / problem+json | A standard JSON error format |
| `Retry-After` | HTTP header telling a client when to try again |
| Backpressure | Saying "too busy" instead of queueing without limit |
| Decorator | A wrapper that adds behaviour around another object |
| OpenAPI | A written description of a REST API |

**Say it in one breath:** I keep the use case free of Spring, wire it by hand in one config class, and return one error shape, but the contract and the code disagree on the 413 and a couple of config details.

---

## Phase 4 — Kafka producers, consumers and Kafka Streams (keys, partitions, Avro serialization, schema evolution gate)

**Analogy: a motorway with lanes.** A topic is the motorway. A partition is one lane. The key is your number plate: cars with the same plate always use the same lane, so they stay in order. More lanes later reshuffles who uses which.

### Topic, partition, key
- A **topic** is a named log. A **partition** is one ordered slice of it. The **key** decides which partition a record lands on, so records with the same key stay in order.
- I key `telemetry.raw.v1` by `sessionId`. `session_start`, heartbeats and `session_end` for one viewing session must stay in order. Kafka guarantees order only within a partition.
- Keying by tenant would give three hot partitions, because there are only three tenants.
- A null key would balance load but lose ordering.
- Cost: aggregating per title later needs a **repartition** (moving data to new keys). I accept that. Ordering is correctness. Repartitioning is performance.

### Avro `Utf8` is not a `String`
- Avro's generated classes decode text as `org.apache.avro.util.Utf8`. That is a different class from `String`. `equals` between them is false and hash codes differ.
- Using a decoded value as a map key, or comparing it to a string, silently misses.
- The codec's javadoc warns about it. The code calls `toString()` at the boundary. `ObservationMapper` converts every field. `AggregateDecoder` has a small `text` helper.
- It is the same `equals` and `hashCode` contract from Phase 2, showing up through a serialization library.

### Producer config for durability
- Settings: `enable.idempotence: true`, `acks: all`, `max.in.flight.requests.per.connection: 5`, `linger.ms` 20, 64 KB batches, lz4 compression, `delivery.timeout.ms` 120 s.
- **Idempotence** makes a producer-side retry safe. The broker discards a record it already appended.
- My Redis claim is a separate layer that handles the client's own retries.
- The publisher sends each event with the session id as key and the event's `occurredAt` as the record timestamp. So Kafka Streams can window on event time without a custom timestamp extractor.
- It returns a `CompletableFuture` from `CompletableFuture.allOf`. The use case waits for every acknowledgement before answering 202.
- The file comment says to verify the exact in-flight limit for idempotence in current Kafka docs. I repeat that advice.
- File: [KafkaEventPublisher.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/kafka/KafkaEventPublisher.java).

### Why changing the partition count moves keys
- A key maps to a partition by a hash modulo the partition count. I used Kafka's own `Utils.murmur2` in a scratch program.
- Against `kafka-clients` 3.9.1: five of six sample keys moved partition when I changed 12 to 18. Only `sess-1` stayed.
- I believe the default partitioner applies the same murmur2 hash to a keyed record. Verify in current Kafka docs.
- This is why the AsyncAPI file says partition count is the one setting you cannot change later. It is also why 12 was chosen above current need.

### The Kafka Streams topology
- It decodes and validates each raw record into a `Decoded` value. It splits into rejected and accepted branches.
- Rejected records go to `telemetry.raw.v1.dlt` (a **dead-letter topic**, a parking place for bad records) with the original bytes and a reason header.
- The accepted branch passes a de-duplicator keyed by event id. It runs before the repartition, so a retry with the same session key lands on the same task.
- Then: re-key by tenant, title and region; group; window over 10 seconds with a 5 second **grace** (how long late events are still accepted); aggregate into an immutable `WindowAccumulator`.
- `suppress(untilWindowCloses)` makes downstream see one final record per window.
- Every operator and store is named. Kafka Streams derives internal topic and store names from topology position. An unnamed operator can orphan state when another operator is added.
- `Suppressed.BufferConfig.unbounded()` is a memory risk I have not measured.
- A quiet partition holds its last window open, because suppression waits for stream time to advance. The ADR states that as a cost.
- File: [TelemetryTopology.java](../../../../../streampulse/services/stream-processor/src/main/java/com/streampulse/processor/adapter/streams/TelemetryTopology.java).

### Is the BACKWARD gate enough to deploy safely (senior)
- No. Be precise about what the gate proves.
- At build time, `SchemaCompatibilityTest` checks that the current schema, as reader, can read data written with a frozen baseline schema.
- It fails the pull request that adds a field without a default, renames a field or narrows a type. Three fixtures prove it rejects. A fourth proves an optional field with a default passes.
- At runtime, the codec builds both writer and reader from the same generated class. Its own javadoc says it does not resolve evolution across versions. That is what a Schema Registry would add.
- My reasoning (not tested with a mixed-version run): Avro binary carries no field names and no schema id. A consumer built from schema v1 reading bytes from v2, or the reverse, will misparse or fail to decode.
- A decode failure in the processor would send the record to the dead-letter topic. A misparse that happens to decode would not. I have not tested which occurs. So the rollout window is a data-loss risk I cannot size.
- ADR-0005 admits the consumers-first deploy order is not enforced by anything. The ADR text that says a registry arrives later is not true of the code today.
- The measured benefit of Avro is real: a heartbeat is 134 bytes against about 409 as JSON. Recorded in the repo from my own measurement.
- Files: [SchemaCompatibilityTest.java](../../../../../streampulse/libs/contracts/src/test/java/com/streampulse/contracts/SchemaCompatibilityTest.java), [AvroBinaryCodec.java](../../../../../streampulse/libs/contracts/src/main/java/com/streampulse/contracts/codec/AvroBinaryCodec.java).

### A breaking change without a registry (senior)
- Use the mechanism ADR-0005 names: a new topic version such as `telemetry.raw.v2`. Producers dual-write. Consumers migrate at their own pace until `v1` is idle.
- For compatible changes: add Schema Registry framing, so the writer schema travels with each record. Or give the codec an explicit writer-schema argument and a version marker in a header.
- Trade-off: operate a registry or a header convention, in return for rolling deploys that do not drop records.
- I have not built either. I would say so in the interview. I would not claim the gate alone makes deploys safe.
- ADR: [0005-topic-and-schema-versioning.md](../../../../../streampulse/docs/adr/0005-topic-and-schema-versioning.md).

### Words you'll hear
| Term | Meaning |
|---|---|
| Topic | A named log of records in Kafka |
| Partition | One ordered slice of a topic |
| Key | Decides the partition, keeps same-key records in order |
| Avro | A compact binary format with a schema |
| `Utf8` | Avro's own text class, not a Java `String` |
| Producer idempotence | Broker discards a record it already stored |
| `acks=all` | Wait until all in-sync replicas have the record |
| Kafka Streams | A library for processing topics in your own app |
| Windowing / grace | Group by time slice; how long late events are accepted |
| Dead-letter topic | A topic for records that cannot be processed |
| Schema Registry | A service that stores schema versions |
| Backward compatible | New schema can read data written with the old one |

**Say it in one breath:** I key by session so each session stays in order, I use idempotent acknowledged producers and a windowed Streams topology, and the build-time BACKWARD gate does not make a mixed-version rollout safe because the codec resolves no versions.

---

## Phase 5 — Reliability patterns in Java (idempotency, outbox with Debezium, poison records, retries)

**Analogy: a post office with a numbered parcel book.** Each parcel has a number, so a re-sent parcel is spotted. A damaged parcel goes to a quarantine shelf. But if the whole sorting machine is down, you do not quarantine parcels. You wait.

### Where idempotency shows up
- Three places.
  - The client generates the `EventId`, validated in a record. A retry carries the same id.
  - The gateway claims that id atomically with Redis `setIfAbsent` before publishing. It releases the claim if the publish fails, so a client's retry is not mistaken for a duplicate.
  - The sink writer uses `INSERT ... ON CONFLICT DO UPDATE` keyed by the aggregate's identity. A redelivered record changes nothing.
- Module 04 argues why each of the three is needed.

### `finally` and the interrupt flag
- A `finally` block runs whether the `try` returned or threw. Releasing the `Semaphore` permit there means a failure can never leak capacity.
- A leaked permit is a permanent loss of throughput. It shows up only as rising latency days later.
- When I catch `InterruptedException`, the thread's interrupt status has been cleared. So I call `Thread.currentThread().interrupt()` to restore it. Otherwise code further up cannot tell the thread was asked to stop.
- During shutdown that is the signal I most need to preserve.

### Writing an outbox row only inside a transaction
- The **outbox pattern**: write the change and the announcement of it in the same database transaction. A separate process (Debezium) then publishes the announcement.
- The port `ConfigChangeOutbox` is implemented by `JdbcConfigChangeOutbox.append`, annotated `@Transactional(propagation = Propagation.MANDATORY)`.
- With `MANDATORY`, a call without an active transaction throws instead of starting one. `REQUIRES_NEW` would let the row commit on its own and outlive a rolled-back change.
- `ChangeRecorder` is called by each service inside its own transaction after the entity is saved. So the version in the announcement is the new one.
- `OutboxAtomicityIT` pins both directions against a real Postgres: a rolled-back change leaves no outbox row, and appending outside a transaction raises `IllegalTransactionStateException`.
- I did not run it today. I read its source.
- `TransactionBehaviourIT` answers the checked-exception question with evidence: the checked failure committed the row, and `rollbackFor` rolled it back.
- Files: [JdbcConfigChangeOutbox.java](../../../../../streampulse/services/control-plane/src/main/java/com/streampulse/controlplane/adapter/out/outbox/JdbcConfigChangeOutbox.java), [TransactionBehaviourIT.java](../../../../../streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/lab/TransactionBehaviourIT.java).

### Poison record vs outage (senior)
- A **poison record** is one that fails every time. An **outage** is the store being down.
- The listener decodes first. It dead-letters anything undecodable, or that the store would reject on every attempt.
- For the rest, `BatchWriter` retries the batch up to the configured attempts with doubling backoff. Then it writes the records one at a time.
  - If some succeed, the store is up and the failures are poison. They are dead-lettered.
  - If none succeed, it cannot tell a bad record from a dead store. It fails them all and lets the listener redeliver.
- The Spring error handler never skips. Its recoverer throws. Every exception is retried with capped exponential backoff and no attempt limit. So an outage is waited out.
- Config values are targets, not measurements: 200 rows or 100 ms per batch, queue 2,000, three flush attempts at 50 ms, and `max.poll.interval.ms` 300,000. A comment says it must exceed the poll budget plus the longest backoff.
- Weak spots:
  - A single poison record alone in a batch looks like an outage.
  - A failing dead-letter publish holds back the acknowledgement. That is deliberate. Skipping would lose the record.
  - The alert engine's rule loader makes the opposite choice. It logs and skips a rule that fails to apply.
- I did not run these integration tests today. Their injected failures are exceptions, not killed processes.
- File: [BatchWriter.java](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java).

### Retries that do not make an incident worse (senior)
- The publisher composes **Retry outside CircuitBreaker outside TimeLimiter**. Every attempt is counted by the breaker. A hanging call is cut by the limiter before the breaker sees it.
- The retry policy ignores three exception types:
  - an open breaker, because retrying cannot succeed inside a sub-second budget;
  - a timeout, because retrying a slow failure multiplies how long the batch holds an in-flight permit;
  - `IllegalArgumentException`, because a rejected batch fails identically.
- Everything else is retried up to three attempts with jittered exponential backoff.
- Honest limit: "everything else" is a blacklist. The file says a whitelist would be safer once both adapters' failure modes are mapped.
- File: [ResilientEventPublisher.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/resilience/ResilientEventPublisher.java).

### Words you'll hear
| Term | Meaning |
|---|---|
| Idempotency | A repeat has no extra effect |
| Outbox pattern | Save the event with the change, publish it separately |
| Debezium | A tool that reads database changes and publishes them to Kafka |
| `Propagation.MANDATORY` | Must already be in a transaction, or fail |
| Poison record | A record that fails every time |
| Dead-letter | A parking place for unprocessable records |
| Circuit breaker | Stops calling a failing service for a while |
| Time limiter | Cuts off a call that takes too long |
| Jittered backoff | Randomised, growing wait between retries |
| Semaphore | A counter that limits how many run at once |

**Say it in one breath:** I make retries safe with an event id, a Redis claim and an upsert, force the outbox write into the caller's transaction with MANDATORY, and tell a poison record from an outage by writing records one at a time.

---

## Phase 6 — Testing (JUnit, Testcontainers integration tests, architecture tests, what the CI runs)

**Analogy: three inspection stages in a factory.** A quick bench check on every part (unit). A full test on a real machine (integration). A blueprint check that the factory layout was not broken (architecture).

### Unit vs integration tests
- By class name. Anything ending in `IT` is an integration test that starts containers. Everything else is a unit test and needs no Docker.
- The convention plugin makes the `test` task exclude `**/*IT.class`. It registers an `integrationTest` task that includes only those. It makes `check` depend on `integrationTest`.
- As I understand Gradle's lifecycle, `build` runs `check`. So CI running `./gradlew build` also runs the integration tests. Verify in current Gradle docs.
- By file name: 149 test classes in `libs`, `services` and `functions`. 32 are `*IT`.
- File: [streampulse.java-conventions.gradle.kts](../../../../../streampulse/build-logic/src/main/kotlin/streampulse.java-conventions.gradle.kts).

### Mock vs stub vs fake
- A **stub** returns canned answers. A **mock** also verifies the calls made on it. A **fake** is a small working implementation, such as an in-memory store.
- I prefer fakes. They let me assert on outcomes (what reached the publisher), not on how my code called a collaborator. The version catalog comment says mocks are used sparingly.
- Six test classes import Mockito, mostly controller tests. Use-case tests use hand-written fakes like `FakePublisher` and `FakeIdempotencyStore`.
- Risk: a fake can drift from the real adapter. That is why each adapter also has an integration test against a real container.

### Testcontainers
- `PostgresIT` is an abstract `@SpringBootTest` base class. It starts one Postgres 16 container per JVM in a static initializer. It registers the URL with `@DynamicPropertySource`. It truncates every table before each test.
- Fast, because the container and Spring context are reused. Trade-off: tests share a database and rely on the truncate for isolation.
- The container starts with `wal_level=logical` so the Debezium test can share it.
- `OutboxAtomicityIT` extends it. It creates a tenant inside a transaction. It asserts the outbox row exists inside the transaction, so the test is not vacuous. Then it throws. Then it asserts both the tenant and the outbox row are gone.
- File: [PostgresIT.java](../../../../../streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/support/PostgresIT.java).

### Injected `Clock`
- Time is a dependency. I inject a `Clock`. A fixed instant makes the test deterministic.
- `EventValidator` uses this for its future-skew rule.
- My scratch example (JUnit 5.12.2, AssertJ 3.27.3, run through the JUnit launcher): two tests found, two succeeded, none failed.

### Testing a Kafka Streams topology without a broker
- `TelemetryTopologyTest` builds the real topology with `TopologyTestDriver`. It runs in memory. It pipes bytes into the input topic and reads the output and dead-letter topics.
- A window closes only when stream time advances. So most tests pipe a later "tick" record. One test asserts that without the tick nothing is emitted.
- I set the state-store cache to zero. The test asserts only what the topology promises, not commit timing.
- The topology is a pure function of its arguments, with an injected `Clock`. That makes this possible.
- File: [TelemetryTopologyTest.java](../../../../../streampulse/services/stream-processor/src/test/java/com/streampulse/processor/adapter/streams/TelemetryTopologyTest.java).

### What CI runs and does not run (senior)
- The workflow runs on pushes to `main` and on pull requests, with a 20 minute timeout on `ubuntu-latest`.
- It sets up JDK 21 and Gradle. It runs `./gradlew spotlessCheck` (a format check). Then `./gradlew build --no-daemon`, which includes the integration tests through `check`. It uploads test and coverage reports.
- Docker is needed for `*IT` classes. GitHub's Ubuntu runners include it as far as I know. Verify that. I have not looked at a CI run's output.
- It does **not** run: the React tests, Terraform validation, the Python checkers under `scripts/`, image builds, or any load test.
- Jacoco produces a report but I found no coverage threshold.
- One detail I derived by reading: the uploaded test report path is `build/reports/tests/test/`. That is the unit-test task's directory. So a failing integration test's HTML report is not uploaded. The console output still carries the full exception, because the convention sets `exceptionFormat = FULL`.
- Numbers: I ran 55 tests today with 0 failures. The repo's own record says control-plane had 102 tests, alert-engine 191, activity-feed 165 and mcp-server 87 with no failures in earlier runs. All on one machine.
- File: [ci.yml](../../../../../streampulse/.github/workflows/ci.yml).

### What `TopologyTestDriver` cannot prove (senior)
- It cannot prove rebalancing, real transactions under `exactly_once_v2`, broker failures or offset commits. There is no broker.
- The repo covers part of that with `StreamProcessorIT` and `StreamProcessorRecoveryIT` against containers. The sink has `NoLossNoDoubleCountIT` and `PoisonRecordIT`. I did not run them today.
- All injected failures are exceptions in the same JVM. Not a killed process or a partitioned network.
- The repo's own resilience notes record that a `kill -9` of the processor mid-window dropped events as expired-window records. These tests do not model that.

### Words you'll hear
| Term | Meaning |
|---|---|
| Unit test | Fast test of one piece, no Docker |
| `*IT` / integration test | Test against real infrastructure in containers |
| Testcontainers | A library that starts real Docker containers for tests |
| Mock / stub / fake | Test stand-ins of increasing realism |
| `TopologyTestDriver` | Runs a Kafka Streams topology in memory |
| Stream time | Time advanced by record timestamps, not the wall clock |
| `Clock` injection | Pass in time so tests control it |
| CI | Automatic build and test on each change |
| Coverage threshold | A minimum test coverage the build enforces |

**Say it in one breath:** Unit tests run fast with fakes and an injected clock, `*IT` classes start real containers, and CI runs both through `build`, but I only ran 55 unit and architecture tests myself and no container test.

---

## Phase 7 — Concurrency, the JVM and operating it (Java 21, shared state, Micrometer, health checks)

**Analogy: a busy bank branch.** Tellers handle customers (threads). A ticket machine limits how many enter (semaphore). A notice board is rewritten as a whole sheet and swapped in, so readers never see half-written text (copy-on-write). At closing time the doors lock first, then tellers finish, then the lights go off.

### Virtual threads
- A **virtual thread** is a lightweight thread scheduled by the JVM onto a small pool of carrier threads. It is final in Java 21. When it blocks on I/O it unmounts, so it costs memory, not an operating-system thread.
- I enable `spring.threads.virtual.enabled` in the ingest gateway, alert engine and activity feed. Their requests block on Kafka, Redis, Postgres or HTTP.
- The ingest gRPC server uses `Executors.newVirtualThreadPerTaskExecutor()`. The alert engine's SSE writers use `Thread.ofVirtual()`.
- The sink writer and stream processor do **not** enable virtual threads.
- The `spring-service` convention sets the property only for test tasks. So I must not say every service runs on them in production.

### `volatile`, `synchronized`, `ReentrantLock`
- `volatile` guarantees visibility and ordering of a single variable across threads. It does not make read-modify-write atomic.
- `synchronized` gives mutual exclusion and visibility with a block-scoped monitor.
- `ReentrantLock` gives the same exclusion with explicit `lock` and `unlock`, timeouts and fairness options.
- I use `volatile` for flags like `closed` in `BatchWriter` and `running` in lifecycle beans. I use `ReentrantLock` where a lock is held around blocking work.
- On Java 21, a virtual thread that blocks inside `synchronized` **pins** its carrier. So I avoid that pattern.
- A later JDK is reported to remove the pinning. I believe it is JDK 24. Verify in current docs.

### Liveness vs readiness
- **Liveness** asks: is the process broken beyond recovery? The only cure Kubernetes has is a restart.
- **Readiness** asks: should it receive traffic right now?
- In the gateway, sink writer and stream processor, only `livenessState` is in the liveness group. Putting Redis there would restart every pod at once when Redis blips. The gateway fails open on Redis anyway.
- The stream processor adds a `streamsState` indicator to readiness only. It counts a rebalance as up, so a rolling deploy does not remove every pod at once.
- During shutdown the gateway flips readiness to refusing traffic, not liveness. Kubernetes then drains the pod instead of restarting it.
- File: [StreamsStateHealthIndicator.java](../../../../../streampulse/services/stream-processor/src/main/java/com/streampulse/processor/config/StreamsStateHealthIndicator.java).

### How `BatchWriter` is thread-safe
- One dedicated platform thread, `batch-flusher`, drains a bounded `ArrayBlockingQueue`. Any number of listener threads call `submit`.
- A `volatile boolean closed` plus a `ReentrantReadWriteLock` make "is it open?" and "enqueue" one step with respect to `close()`.
- Submitters take the shared read lock. `close()` takes the write lock only to set the flag.
- Without it: `submit` could see the writer open. `close()` could set the flag and let the flusher exit on an empty queue. Then `submit` could enqueue a record nothing would ever write.
- I chose a read-write lock over `synchronized` because `submit` blocks in `offer`. The exclusion has to survive a blocking call.
- Trade-off: `close()` waits for in-flight offers, bounded by the offer timeout.
- File: [BatchWriter.java](../../../../../streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java).

### Sharing read-mostly state without locking the hot path
- `RuleBook` holds the alert rules in a `volatile` field pointing to an immutable snapshot.
- Readers on the evaluation path read the field once and use that snapshot. No lock.
- Writers take a `ReentrantLock`, build a new snapshot from copies of the maps, and publish it with one volatile write.
- A write replaces one tenant's rules and rebuilds that tenant's dependency graph. A cyclic rule set throws before the book changes.
- Cost: allocation per write. Fine, because rule changes are rare and reads happen for every observation.
- This is **copy-on-write** with a volatile reference. Same idea as `List.copyOf` in a compact constructor: build the new immutable value, then publish it.
- File: [RuleBook.java](../../../../../streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/RuleBook.java).

### Operating under load and at shutdown (senior)
- Concurrency is bounded at the edges:
  - a fair `Semaphore` of 64 in-flight batches with a 250 ms permit wait returns 503 instead of queueing;
  - the sink's buffer holds 2,000 records with a 1 s offer timeout;
  - the query API's blocking calls run on a fixed pool with a bounded queue that rejects when full.
- Shutdown is ordered with `SmartLifecycle` phases:
  - readiness flips first;
  - the HTTP connector stops;
  - the gateway waits for permits to return, up to a 20 s drain timeout;
  - the sink closes its writer after the Kafka listener container stops.
- The phase numbers in the class comments are mine. I did not verify Boot's internal phase values.
- Measured numbers, from the repo's own record, on one Apple M2 Pro with a single broker: ingest p99 68.7 ms at 1,500 events per second. Clean at 40,000 events per second. 503s from 45,000. The load generator shared the CPU. So I would not quote either as capacity.
- Heap moved between 45.5 and 313 MiB with 34 to 35 threads while refusing 105,800 events.
- Unproven: virtual-thread pinning. The ADR says to measure with `-Djdk.tracePinnedThreads`. The interview notes record that this has not been done. So I do not claim the risk is absent or present.
- I also have not measured drain time under a real SIGTERM.
- Files: [IngestDrainLifecycle.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/lifecycle/IngestDrainLifecycle.java), [MicrometerIngestMetrics.java](../../../../../streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/config/MicrometerIngestMetrics.java). Numbers: [06-numbers.md](../../../../../streampulse/docs/interview/06-numbers.md). ADR: [0006-virtual-threads-over-webflux.md](../../../../../streampulse/docs/adr/0006-virtual-threads-over-webflux.md).

### One lock across evaluate and deliver (senior)
- `AlertProcessor` has two threads: the aggregate listener and the absence sweeper. Both evaluate, then drain an outbox to delivery channels.
- One lock across the three steps keeps changes entering the outbox in the order the engine produced them.
- The drain calls channels that block on the network. `ReentrantLock` is the safer primitive on Java 21 than `synchronized`, which would pin a virtual thread's carrier.
- Caveat: the alert engine's Kafka consumer is a platform thread. So the pinning argument is defensive there.
- A single lock serialises all evaluation. That caps throughput at one thread's worth. I have not measured that ceiling.
- A related unproven point: `BatchWriter.flusher` is a plain non-volatile field assigned after construction and read in `close()`. I believe Spring's singleton registration publishes it safely. I have not verified it.
- File: [AlertProcessor.java](../../../../../streampulse/services/alert-engine/src/main/java/com/streampulse/alert/application/AlertProcessor.java).

### Words you'll hear
| Term | Meaning |
|---|---|
| Virtual thread | A very light JVM-managed thread |
| Carrier thread | The real OS thread a virtual thread runs on |
| Pinning | A virtual thread stuck holding its carrier while blocked |
| `volatile` | A field whose writes are visible to all threads |
| `ReentrantLock` | An explicit lock with timeouts and fairness |
| Copy-on-write | Build a new copy, then swap it in |
| Liveness / readiness | Is it broken? / Can it take traffic now? |
| Micrometer | A metrics library for Java apps |
| `SmartLifecycle` | Spring hook for ordered start and stop |
| Drain | Finish in-flight work before shutting down |
| p99 | The latency 99 percent of requests beat |

**Say it in one breath:** I bound concurrency with a semaphore and bounded queues, share rules through a volatile immutable snapshot, shut down in a set order, and virtual-thread pinning is still unmeasured.

---

## Mix-ups to avoid

- **Liveness vs readiness.** Liveness failing means restart. Readiness failing means stop sending traffic. Do not put Redis in liveness.
- **Utf8 vs String.** An Avro-decoded text value is not equal to a Java `String`. Call `toString()` at the boundary.
- **BACKWARD gate vs safe rollout.** The gate is a build-time check. The runtime codec resolves no versions.
- **MANDATORY vs REQUIRES_NEW.** MANDATORY fails with no transaction. REQUIRES_NEW commits on its own and can outlive a rollback.
- **Mock vs fake.** A mock verifies calls. A fake is a working stand-in. I prefer fakes.
- **Poison record vs outage.** If some records succeed one by one, the failures are poison. If none succeed, treat it as an outage.

## What I built vs what I only know

**Built ([L], my own, in the `streampulse` repo):**
- A Java 21 Gradle multi-module build: shared kernel, Avro contracts, eight Spring Boot services and one function, joined by Kafka, Postgres and Redis.
- Hexagonal packages with ArchUnit rules, value-object records, sealed result types, a Kafka Streams topology, a transactional outbox, a batch sink with poison handling, and tests at every level.
- Some commits are co-authored with Claude. I defend each line from the code.
- Run today: 55 unit and architecture tests in one offline Gradle invocation. All passed.

**Not claimed:**
- Not every service runs on virtual threads. Only the gateway, alert engine and activity feed enable them in `application.yml`. The convention plugin sets the property for test tasks only.
- The architecture rules are not uniform or proven. Sets differ per module, `libs/platform` cannot see service classes, the clock rule exists in two modules only, and I have not mutated a rule.
- The schema gate does not make a rollout safe. The codec does not resolve schema versions. I have not run a mixed-version test.
- The pipeline does not compute payload-driven metrics. `AvroEventMapper` sets the payload to null.
- The OpenAPI document does not match the code exactly. It lists a 413 where the code returns 400. `max-batch-size` is bound but never read.
- Kinesis is not the default path. `streampulse.backbone` defaults to Kafka (ADR-0012). A comment in the gateway's `build.gradle.kts` still says Kinesis is the default.
- The ADR statement that a Schema Registry arrives in a later phase is not true of the code. ADR-0012 and the codec record that there is none.
- The `IngestDrainLifecycle` double registration (`@Component` plus `@Bean`) is not verified safe. I believe the `@Bean` definition replaces the scanned one. The fix is to remove the annotation.
- Throughput, latency and heap numbers need their conditions: one Apple M2 Pro, one broker, replication factor 1, load generator sharing the CPU.
- Virtual-thread pinning was not measured. Whether JEP 491 applies to the JDK I ship is marked verify. The measurement task was not done.
- No `*IT` class was run today. None of the Testcontainers tests passed in my run.
- Not production use. This is a learning and portfolio system. Its scenarios are labelled fictional in `CLAUDE.md`.
