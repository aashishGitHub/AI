# Module 13 — Java backend (Spring, Kafka, testing) via streampulse

> This module is about the Java 21 backend I built in `streampulse`: a Gradle multi-module build with a shared kernel (`libs/platform`), Avro contracts (`libs/contracts`), eight Spring Boot services and one Spring Cloud Function, joined by Kafka, Postgres and Redis. Every lane is **[L]** because I built it, but some commits are co-authored with Claude, so I must be able to defend every line, including the lines that contradict my own conventions (this guide names several). Paths below are relative to `/Users/aashishkumar/Documents/GitHub/`, and the build is Gradle with the Kotlin DSL, not Maven. On 2026-10-20 I ran one Gradle invocation offline (`:libs:platform:test`, `:libs:contracts:test`, and `:services:ingest-gateway:test` filtered to `IngestServiceTest` and `IngestArchitectureRulesTest`): it reported 55 passed, 0 failed and `BUILD SUCCESSFUL in 30s`. I did not run any Testcontainers `*IT` class, so every statement about an integration test comes from reading its source. Numbers are labelled by origin: config, recorded in the repo's own docs (one developer machine), derived by counting, or produced by my own small programs in a scratch directory.

## Phases at a glance

| Phase | Purpose in one sentence | Main code |
|---|---|---|
| 1. Project structure and architecture rules | Split the system into modules and hexagonal packages, and make the dependency direction a failing test instead of a diagram. | `settings.gradle.kts`, `*ArchitectureRulesTest.java` |
| 2. Domain modelling in modern Java | Use records, sealed types and validating constructors so that an invalid value cannot exist. | `EventId.java`, `TenantId.java`, `IngestCommand.java`, `Validation.java`, `Evaluators.java` |
| 3. Spring service design | Keep the use case free of Spring, wire it in one config class, and publish REST contracts and one error shape. | `IngestService.java`, `IngestConfig.java`, `IngestExceptionHandler.java`, `api/openapi/*.yaml` |
| 4. Kafka producers, consumers and Kafka Streams | Choose keys and partitions for ordering, encode raw Avro, and guard schema changes at build time. | `KafkaEventPublisher.java`, `TelemetryTopology.java`, `AvroBinaryCodec.java`, `SchemaCompatibilityTest.java` |
| 5. Reliability patterns in Java | Implement idempotency, the outbox, poison-record handling and retries in code that a unit test can drive. | `JdbcConfigChangeOutbox.java`, `BatchWriter.java`, `SinkConfig.java`, `outbox-connector.json` |
| 6. Testing | Run fast unit tests on every change, real containers in `*IT` classes, and architecture and contract tests in the same build. | `java-conventions.gradle.kts`, `PostgresIT.java`, `TelemetryTopologyTest.java`, `ci.yml` |
| 7. Concurrency, the JVM and operating it | Bound concurrency, share state safely, expose health and metrics, and shut down in order. | `BatchWriter.java`, `RuleBook.java`, `IngestDrainLifecycle.java`, `MicrometerIngestMetrics.java` |

## Phase 1 — Project structure and architecture rules (modules, hexagonal packages, dependency direction enforced by tests)

### 🟢 Beginner

**Q:** How is the repository organised, and why is it more than one module?

**A:** It is one Gradle build with twelve included projects: two libraries, eight services, one function and a load generator. `libs:platform` holds the value objects every service shares, such as `TenantId` and `EventId`, and `libs:contracts` holds the Avro schemas, the generated classes and the codec. Each service declares `implementation(project(":libs:platform"))` and `implementation(project(":libs:contracts"))`, so a service is a leaf that nothing else compiles against. I checked by searching the build files that no service depends on another service, only on the two libraries. The reason for the split is that producers and consumers must code against the same contract without one service's jar dragging in another service's internals. Shared build behaviour lives in convention plugins in an included `build-logic` build, so a service opts in with one `id("streampulse.spring-service")` line, which pins the Java 21 toolchain, compiler lint flags, JUnit, ArchUnit and actuator once.

**Q:** What does hexagonal architecture mean in this code, in one minute?

**A:** Each service has a `domain` package for rules and ports, an `application` package for use cases, `adapter.in` for things that call me such as REST controllers and Kafka listeners, `adapter.out` for things I call such as Kafka, Redis and JDBC, and `config` for wiring. Dependencies point inward, so the domain declares an interface like `EventPublisher` and an adapter implements it. The practical benefit is that I can test the use case with plain `new` and a fake, and I can swap an adapter, as I did with the Kinesis publisher beside the Kafka one. The cost is more files: about 341 main source files across the build, counted by file name.

### 🟡 Intermediate

**Q:** How do you enforce the dependency direction, and where do the rules live?

**A:** Enforcement is ArchUnit, which reads compiled bytecode and expresses architecture rules as ordinary JUnit tests. The rules live in each module's own test directory, not in `libs/platform`, because ArchUnit scans the test classpath and `libs/platform` does not depend on any service, so it cannot see their classes; the ingest test says exactly this in its own header. The core rule for the gateway forbids the domain and application packages from touching gRPC, protobuf, servlet or Spring web types, another forbids `adapter.in` from reaching `adapter.out`, and a third forbids adapters from naming the `IngestService` class instead of its `IngestUseCase` port.


**Source:** `streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/IngestArchitectureRulesTest.java:84-101`

```java
    @Test
    @DisplayName("adapters depend on the PORT, not on IngestService")
    void adaptersDependOnThePortNotTheImplementation() {
        // IngestUseCase is an interface with a single implementation, which invites "why not
        // just inject the class?". This is the answer: depending on the interface is what
        // allows a test to substitute a recording double (see GrpcIngestInProcessTest) and
        // what keeps the adapters from reaching implementation details such as the permit
        // count. Only the composition root and the drain lifecycle may name the class.
        ArchRule rule = noClasses()
                .that()
                .resideInAPackage("..adapter..")
                .should()
                .dependOnClassesThat()
                .haveFullyQualifiedName("com.streampulse.ingest.application.IngestService")
                .because("an adapter that knows the implementation can reach past the port");

        rule.check(PRODUCTION_CLASSES);
    }
```

**Illustrative (not from the repo):** a slice rule that I wrote and ran once against the compiled ingest classes, to see whether the top-level packages form a cycle. It is not part of the build.

```java
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.EvaluationResult;
import com.tngtech.archunit.library.dependencies.SlicesRuleDefinition;

public class CycleRule {
    public static void main(String[] args) {
        var classes = new ClassFileImporter()
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
                .importPath(args[0]);
        var rule = SlicesRuleDefinition.slices()
                .matching("com.streampulse.ingest.(*)..")
                .should()
                .beFreeOfCycles();
        EvaluationResult result = rule.evaluate(classes);
        System.out.println("classes=" + classes.size() + " violations=" + result.hasViolation());
        result.getFailureReport().getDetails().stream().limit(6).forEach(System.out::println);
    }
}
```

I compiled this with the cached ArchUnit 1.4.1 jar and ran it against `services/ingest-gateway/build/classes/java/main`: it reported 47 classes and no violations, from one run on my machine. When I talk about it I say it is a candidate rule that currently passes, not a rule the repo enforces.

### 🔴 Senior

**Q:** How do you know these rules guard anything, and where are the gaps?

**A:** I do not fully know, and the honest answer is that the rule sets are uneven. Counting `@DisplayName` annotations, there are 51 rule tests across ten files (nine modules plus `libs/platform`), but they differ: the ingest set forbids protocol types in the core and forbids adapter shortcuts, yet it has no rule that the domain is free of Spring, Kafka or Redis types and no field-injection rule, while control-plane, activity-feed, alert-engine and sink-writer do have those. The clock rule, which says production code must not call `Instant.now()`, exists only in control-plane and mcp-server, and ingest-gateway still calls `Instant.now()` in `IngestController` and `AvroEventMapper` and `System.currentTimeMillis()` in the Redis rate limiter, which contradicts the convention in `CLAUDE.md`. In `libs/platform` the adapter-direction rule is declared with `allowEmptyShould(true)` and has no `..adapter.in..` classes to examine, so it passes vacuously. I have not mutated any architecture rule to see it fail, so I cannot claim they would catch a regression; that is not measured.


**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/ControlPlaneArchitectureRulesTest.java:92-104`

```java
    @Test
    @DisplayName("production code never reads the wall clock directly")
    void noDirectClockUse() {
        ArchRuleDefinition.noClasses()
                .that()
                .resideOutsideOfPackage("..config..")
                .should()
                .callMethod(java.time.Instant.class, "now")
                .orShould()
                .callMethod(java.time.LocalDateTime.class, "now")
                .because("time comes from the injected Clock so it can be controlled in tests")
                .check(PRODUCTION);
    }
```

**Follow-up they will ask:** Why not one shared rules library that every service applies?

**A:** That is the obvious refactor and I did not build it. The rules would become a test-fixtures module that takes a root package, and each service would call it with its own exceptions, which removes the drift I just described. I stopped at per-module copies because each phase added the rule protecting what it had just built, and the cost of that choice is the unevenness. The trade-off I would accept is a little less flexibility per service in return for one place to add a rule, and I would add the clock rule and the "domain free of Spring, Kafka, Redis" rule there first.

## Phase 2 — Domain modelling in modern Java (records, immutability, validation in constructors, value objects)

### 🟢 Beginner

**Q:** Why are `EventId` and `TenantId` records and not plain strings?

**A:** A bare string cannot say what it means, so a call like `publish(titleId, tenantId)` compiles with the arguments swapped, and with a tenant id that swap is a data leak. A record gives me a distinct type, an automatic constructor, accessors, `equals`, `hashCode` and `toString`, and it is implicitly final and shallowly immutable. I put validation in the compact constructor, so an `EventId` that exists is always a canonical lowercase UUID and a `TenantId` that exists is always lowercase alphanumerics with internal hyphens. Everything downstream can then trust the value without re-checking it.

**Q:** How do `equals` and `hashCode` work, and why does that matter for a `HashMap` key?

**A:** The contract is that equal objects must return equal hash codes, and a `HashMap` uses the hash code to pick a bucket and then `equals` to find the right entry inside it. If I override `equals` and forget `hashCode`, two equal keys can land in different buckets and the map treats them as different keys. A record derives both methods from all its components, which is why I can use `TenantId` or `AggregateKey` as a map key safely. Recent JDKs convert a heavily collided bucket into a tree; I am not certain of the exact thresholds, so verify them in the current docs before quoting.

**Q:** Checked versus unchecked exceptions: which do you throw, and why does it matter with transactions?

**A:** A checked exception must be declared or caught, while an unchecked one extends `RuntimeException` and need not be. My validating constructors throw `IllegalArgumentException`, and the control-plane domain exceptions such as `NotFoundException` and `InvalidInputException` extend `RuntimeException`, so service signatures stay clean and the web layer maps them to status codes in one place. It matters with Spring because `@Transactional` rolls back on unchecked exceptions by default but commits on checked ones. I did not take that from the documentation: `TransactionBehaviourIT` runs against a real Postgres and asserts that a checked failure still commits the row unless `rollbackFor` is set.

### 🟡 Intermediate

**Q:** Show me validation and normalisation in a compact constructor.

**A:** The compact constructor runs before the fields are assigned, so it is the natural place to reject bad input and to reassign the parameter to its canonical form. In `EventId` I require non-null, parse with `UUID.fromString`, compare the round-tripped text with the input because the JDK parser is lenient about some malformed strings, rethrow with the original cause so a bad client payload does not look like an internal error, and finally lowercase with `Locale.ROOT` so the Redis dedup key is stable. `TenantId` does the same with a regex and a 32-character limit, and it trims and lowercases before validating so that `" StreamFlix "` is accepted and stored as `streamflix`.


**Source:** `streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java:48-69`

```java
    public EventId {
        Objects.requireNonNull(value, "eventId must not be null");

        // Parse to validate, then discard the result. UUID.fromString is the authoritative
        // check — a hand-rolled regex would accept malformed input that the JDK rejects.
        //
        // Note: UUID.fromString is historically lenient about some malformed inputs, so we
        // also compare the round-tripped form. If parsing and re-printing does not reproduce
        // the input, the input was not canonical.
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw new IllegalArgumentException("eventId is not a canonical UUID: '" + value + "'");
            }
        } catch (IllegalArgumentException e) {
            // Rethrow with context. Swallowing the cause here would make a bad client
            // payload look like an internal error in the logs.
            throw new IllegalArgumentException("eventId must be a valid UUID, was: '" + value + "'", e);
        }

        value = value.toLowerCase(java.util.Locale.ROOT); // canonical form for dedup keys
    }
```

**Illustrative (not from the repo):** the same idea in a few lines, showing why normalising in the constructor makes `equals` and the map behave.

```java
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ValueObjects {
    record Region(String value) {
        Region {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("region must not be blank");
            }
            value = value.trim().toLowerCase(Locale.ROOT);
        }
    }

    record Batch(List<String> ids) {
        Batch {
            ids = List.copyOf(ids);
        }
    }

    sealed interface Verdict permits Accepted, Rejected {}

    record Accepted() implements Verdict {}

    record Rejected(String reason) implements Verdict {}

    static String describe(Verdict v) {
        return switch (v) {
            case Accepted a -> "ok";
            case Rejected r -> "rejected: " + r.reason();
        };
    }

    public static void main(String[] args) {
        var a = new Region(" US-East-1 ");
        var b = new Region("us-east-1");
        System.out.println(a.equals(b) + " " + (a.hashCode() == b.hashCode()) + " " + a);

        Map<Region, Integer> counts = new HashMap<>();
        counts.merge(a, 1, Integer::sum);
        counts.merge(b, 1, Integer::sum);
        System.out.println(counts);

        var source = new java.util.ArrayList<>(List.of("e1", "e2"));
        var batch = new Batch(source);
        source.add("e3");
        System.out.println(batch.ids());
        try {
            batch.ids().add("x");
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable view");
        }

        System.out.println(describe(new Rejected("blank session")));
    }
}
```

I compiled and ran this with Java 21: the two regions are equal, the map holds one entry with count 2, and the batch keeps its original two ids after the source list grows. I talk about it as the reason a record with a normalising constructor is safe as a key, and `List.copyOf` in a compact constructor is the same defensive copy that `IngestCommand` makes.

**Q:** Why sealed interfaces and pattern-matching switches, and where do you use them?

**A:** A sealed interface closes the set of subtypes, so a `switch` over it needs no `default` and the compiler fails the build when I add a new subtype and forget a branch. I use it for the result of validating or decoding a record: `Validation` has `Valid` and `Invalid`, and the Kafka decoders return a sealed `Decoded` with `Valid` and `Rejected`. In the alert engine `Evaluators` switches over the sealed `Condition`, and its comment says it replaced a registry map for exactly this compile-time reason. Java 21 pattern matching for `switch` is final, but I use only type patterns; I searched and found no record deconstruction patterns and no `when` guards in main code.


**Source:** `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/evaluator/Evaluators.java:29-35`

```java
    public Verdict onObservation(Condition condition, Optional<Observation> previous, Observation current) {
        return switch (condition) {
            case Threshold t -> threshold.onObservation(t, previous, current);
            case RateOfChange r -> rateOfChange.onObservation(r, previous, current);
            case Absence a -> absence.onObservation(a, previous, current);
        };
    }
```

When I talk about these two I say that the first removes a registry that could silently miss a case, and the second is the algebraic result type that lets a topology branch without exceptions for control flow.

### 🔴 Senior

**Q:** Where does your domain model fall short, and what would you change?

**A:** There are three real gaps. First, the telemetry payload is dropped: the Avro schema defines six typed payload variants, `IngestEvent.payload` is an `Object`, and `AvroEventMapper` calls `setPayload(null)` with a comment that variants land later, so the processor computes only distinct sessions and the error ratio from the event type, never anything payload-driven. Second, `WindowAccumulator` is immutable and copies its session set on every event, which is O(sessions) per update, and its own comment says a sketch such as HyperLogLog would replace it at scale; I have not measured the cost, so it is a stated trade, not a number. Third, tenant validation happens in several places on purpose: the controller via `TenantResolver`, `EventValidator` in the processor, and `AggregateKey.of`, so a malformed id from any producer is rejected, at the price of repeating the check on every hop. The boundary of my claim is that value objects protect the shape of an id, not its authorization; the tenant still comes from the verified JWT claim.

**Follow-up they will ask:** Why does `IngestCommand` take `tenantId` as a separate argument instead of a field of each event?

**A:** Because the tenant must come from the verified token and never from the request body, and a separate constructor argument means the wire format cannot supply it even by accident. The DTO has no tenant field at all, so there is nothing to mis-trust. The record also copies the event list with `List.copyOf`, which rejects null elements and freezes the batch after validation. The trade-off is one more parameter at every construction site, which I accept because a cross-tenant write is the worst failure this system can have.


**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/domain/IngestCommand.java:36-46`

```java
    public IngestCommand {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(events, "events");
        Objects.requireNonNull(receivedAt, "receivedAt");
        if (events.isEmpty()) {
            throw new IllegalArgumentException("a batch must contain at least one event");
        }
        // Defensive copy: the caller must not be able to mutate the batch after we have
        // validated it. `List.copyOf` also rejects nulls, which is a free extra check.
        events = List.copyOf(events);
    }
```

## Phase 3 — Spring service design (ports and adapters, configuration, REST/OpenAPI contracts, error handling)

### 🟢 Beginner

**Q:** What is dependency injection, and why do you use constructor injection only?

**A:** Dependency injection means a class receives the collaborators it needs instead of creating them, so I can hand it a fake in a test. With constructor injection the dependencies are `final` fields, the class cannot be built half-wired, and a circular dependency fails at startup instead of at the first call. Field injection hides the dependency list and needs reflection or a Spring context to test. That is why `CLAUDE.md` says constructor injection only, and why several services have an ArchUnit rule against fields annotated with `@Autowired`. The test classes do use `@Autowired` fields, and that is allowed because the rules scan production classes only.

**Q:** Why are your ports interfaces and not abstract classes?

**A:** An interface describes a capability with no state, and a class can implement many of them, while an abstract class gives a single inheritance slot and can carry state I do not want in a port. `EventPublisher`, `IdempotencyStore` and `RateLimiter` are interfaces the domain owns, and the Kafka, Redis and Kinesis adapters implement them. Java 8 added default methods to interfaces, but I keep ports pure so that a test double is a few lines. `RateLimiter` does expose a static `allowAll()` that the unit tests use, which is a small convenience I accepted.

### 🟡 Intermediate

**Q:** Walk me from an HTTP request to a Kafka record in the gateway.

**A:** The controller takes the validated request body and the `Authentication`, asks `TenantResolver` for the tenant from the verified JWT, maps the DTOs to a domain `IngestCommand`, calls the `IngestUseCase` port and returns 202. The use case checks the quota first, acquires a permit from a fair `Semaphore`, claims the event ids in Redis, publishes through the `EventPublisher` port and waits for the broker acknowledgement. `IngestConfig` is the only place that knows which publisher is behind the port: a property selects Kafka by default or the Kinesis adapter, and either is wrapped in the same `ResilientEventPublisher` decorator. The controller has no business logic by design, so a parity test can assert that gRPC and REST produce the same Kafka records.


**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestController.java:53-68`

```java
    @PostMapping(path = "/v1/events:batch", consumes = "application/json", produces = "application/json")
    ResponseEntity<IngestDtos.BatchAcceptedResponse> ingestBatch(
            @Valid @RequestBody IngestDtos.EventBatchRequest request,
            // Optional: per-event eventId already provides idempotency. This lets a client
            // short-circuit a whole retried batch without us deduplicating 500 ids one by one.
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey,
            // The tenant comes from the VERIFIED token, never the body or a client-set
            // header (REQ-IG-07/08). Spring Security has already validated the signature,
            // issuer and expiry before this method runs.
            Authentication authentication) {

        TenantId tenant = tenantResolver.resolve(authentication);

        IngestCommand command = new IngestCommand(tenant, toDomain(request.events()), Instant.now());

        IngestResult result = ingest.ingest(command);
```

I use these two to show the seam: the controller names only ports, and the one conditional bean names the concrete adapter.

**Q:** How do you handle errors in the REST layer?

**A:** One `@RestControllerAdvice` per service turns exceptions into RFC 7807 `application/problem+json`, so a client parses one error shape. In the gateway, `BackpressureException` becomes 503 with `Retry-After`, `QuotaExceededException` becomes 429 with `Retry-After`, `PublishUnavailableException` becomes 503, bean-validation failures and `IllegalArgumentException` become 400, and `IllegalStateException` becomes a 500 with a deliberately generic detail. The control plane maps its own domain exceptions: not found to 404, already exists and conflict to 409, a rule violation to 422, invalid input to 400, and an optimistic-lock failure to 409. I log backpressure at debug and an unexpected failure at error, because designed rejection must not page anyone.


**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestExceptionHandler.java:74-91`

```java
    /** Quota exhausted: the tenant's own limit, not our capacity. */
    @ExceptionHandler(QuotaExceededException.class)
    ResponseEntity<ProblemDetail> handleQuotaExceeded(QuotaExceededException e) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.TOO_MANY_REQUESTS, "Tenant quota exceeded");
        problem.setType(URI.create(PROBLEM_BASE + "quota-exceeded"));
        problem.setTitle("Quota exceeded");

        long seconds = Math.max(1, e.retryAfter().toSeconds());
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.RETRY_AFTER, String.valueOf(seconds));

        // DEBUG: a throttled tenant is the system working, not failing.
        log.debug("Throttled: {}", e.getMessage());

        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .headers(headers)
                .body(problem);
    }
```

When I talk about this I point at the 429 versus 503 split, which the file explains: a quota breach is the tenant's problem and a saturated gateway is mine, and a client reacts differently to each.

### 🔴 Senior

**Q:** Why wire the use case by hand with no `@Service`, and where is the design inconsistent or wrong?

**A:** I wired `IngestService`, `KafkaEventPublisher` and `RedisIdempotencyStore` explicitly in `IngestConfig` so each can be built with plain `new` in a unit test, and `IngestServiceTest` runs the whole idempotency and backpressure suite, including a 200-iteration race test, without starting Spring. The trade-off is one large config class, and the control plane deliberately does the opposite: its services carry `@Service` and `@Transactional`, because a transaction needs a Spring-managed proxy and the outbox rule depends on it. The inconsistencies are real. `IngestDrainLifecycle` is annotated `@Component` and is also built by an `@Bean` method of the same name with a cast to `(IngestService)`; I believe Spring lets the `@Bean` definition silently replace the scanned one, but verify that in current docs, and the clean fix is to delete the annotation. The property `streampulse.ingest.max-batch-size` is bound and validated but never read, while the DTO hard-codes `@Size(max = 500)`. And the OpenAPI document lists a 413 for an oversized batch while the code and `IngestEndToEndIT` return 400, so the contract and the behaviour disagree. I ran the unit tests and they passed, but the contract test only asserts that 202, 400 and 429 exist, so it cannot catch that mismatch.


**Source:** `streampulse/api/openapi/ingest-v1.yaml:70-74`

```yaml
        '413':
          description: Batch exceeds 500 events
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ProblemDetail' }
```

**Follow-up they will ask:** Isn't hand wiring just reimplementing Spring, and what do you lose?

**A:** I lose component scanning convenience and I gain testability and a single reviewable composition root, which is the standard argument for a composition root. I also lose automatic detection of a missing bean until startup, which the `*WiringTest` classes that most services have partly cover; I did not read them closely, and the gateway has none. The boundary of the claim is that this works for classes with no need for proxies. As soon as I need `@Transactional`, `@Cacheable` or similar, the class must be a Spring bean, which is exactly why control-plane differs. A decorator such as `ResilientEventPublisher` is also deliberate: an annotation-based circuit breaker would need a proxy and would not apply to a class built with `new`.

## Phase 4 — Kafka producers, consumers and Kafka Streams (keys, partitions, Avro serialization, schema evolution gate)

### 🟢 Beginner

**Q:** What are a topic, a partition and a key, and why do you key raw telemetry by `sessionId`?

**A:** A topic is a named log, a partition is one ordered slice of it, and the key decides which partition a record lands on, so records with the same key stay in order. I key `telemetry.raw.v1` by `sessionId` because `session_start`, heartbeats and `session_end` for one viewing session must stay in order, and Kafka guarantees order only within a partition. Keying by tenant would give three hot partitions because there are only three tenants, and a null key would balance load but lose ordering. The cost is that aggregating per title later needs a repartition, which I accept because ordering is a correctness property and repartitioning is a performance cost.

**Q:** Why does a decoded Avro string not equal a Java `String`, and what bug would that cause?

**A:** Avro's generated classes decode text as `org.apache.avro.util.Utf8`, which is a different class from `String`, so `equals` between them is false and their hash codes differ. If I used a decoded value directly as a map key or compared it to a string, the lookup would silently miss. The codec's javadoc warns about this, and the code calls `toString()` at the boundary: `ObservationMapper` converts every field and `AggregateDecoder` has a small `text` helper. It is the same equals-and-hashCode contract from Phase 2, showing up through a serialization library.

### 🟡 Intermediate

**Q:** How is the producer configured for durability, and how does the publisher use it?

**A:** The producer sets `enable.idempotence: true`, `acks: all`, `max.in.flight.requests.per.connection: 5`, a 20 ms `linger.ms`, 64 KB batches, lz4 compression and a 120 s `delivery.timeout.ms`. Idempotence makes a producer-side retry safe because the broker discards a record it already appended, and my Redis claim is a separate layer that handles the client's own retries. The publisher sends each event with the session id as the key and the event's `occurredAt` as the record timestamp, so Kafka Streams can window on event time without a custom timestamp extractor. It returns a `CompletableFuture` from `CompletableFuture.allOf`, so the use case waits for every acknowledgement before answering 202. The comment in the file says to verify the exact in-flight limit for idempotence in the current Kafka docs, and I repeat that advice.


**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/kafka/KafkaEventPublisher.java:70-85`

```java
        // The KEY is what decides the partition, and therefore the ordering guarantee.
        // sessionId keeps one viewing session on one partition. See specs/01-contracts/design.md.
        //
        // The record TIMESTAMP is the event's occurredAt, not the broker's append time.
        // Kafka Streams windows on the record timestamp by default, so stamping it here
        // gives the processor event time without a custom extractor that decodes the
        // payload a second time. Requires the topic's message.timestamp.type=CreateTime,
        // which is the default.
        var record = new ProducerRecord<>(topic, null, event.occurredAt().toEpochMilli(), event.partitionKey(), value);
        return kafka.send(record).whenComplete((result, failure) -> {
            if (failure != null) {
                // Log the KEY, never the payload: payloads are large and may carry data we
                // should not spray into logs.
                log.error("Failed to publish event key={} to {}", event.partitionKey(), topic, failure);
            }
        });
```

**Illustrative (not from the repo):** how a key maps to a partition and why raising the partition count moves keys. It uses Kafka's own `Utils.murmur2` from the clients jar.

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.utils.Utils;

public class Partitions {
    static int partition(String key, int partitions) {
        byte[] bytes = key.getBytes(StandardCharsets.UTF_8);
        return Utils.toPositive(Utils.murmur2(bytes)) % partitions;
    }

    public static void main(String[] args) {
        String[] sessions = {"sess-1", "sess-2", "sess-3", "sess-4", "sess-5", "sess-6"};
        for (String s : sessions) {
            System.out.println(s + " -> 12 partitions: " + partition(s, 12) + ", 18 partitions: " + partition(s, 18));
        }
    }
}
```

I compiled and ran this against `kafka-clients` 3.9.1: five of the six sample keys moved partition when I changed 12 to 18, and only `sess-1` stayed. I believe the default partitioner applies the same murmur2 hash to a keyed record, but verify that in the current Kafka docs. This demo is why the AsyncAPI file says partition count is the one setting you cannot change later, and why 12 was chosen above current need.

**Q:** Walk me through the Kafka Streams topology.

**A:** It decodes and validates each raw record into a `Decoded` value, splits it into rejected and accepted branches, and sends the rejected ones to `telemetry.raw.v1.dlt` with the original bytes and a reason header. The accepted branch passes a de-duplicator keyed by event id, which runs before the repartition so that a retry with the same session key lands on the same task. It then re-keys by tenant, title and region, groups, windows over 10 seconds with a 5 second grace, aggregates into an immutable `WindowAccumulator`, and uses `suppress(untilWindowCloses)` so downstream sees one final record per window. Every operator and store is named, because Kafka Streams derives internal topic and store names from topology position and an unnamed operator can orphan state when another operator is added.


**Source:** `streampulse/services/stream-processor/src/main/java/com/streampulse/processor/adapter/streams/TelemetryTopology.java:104-123`

```java
                .selectKey(
                        (key, event) -> AggregateKey.of(ObservationMapper.toObservation(event))
                                .asString(),
                        Named.as("key-by-aggregate"))
                .groupByKey(Grouped.with("by-aggregate-key", Serdes.String(), eventSerde))
                .windowedBy(TimeWindows.ofSizeAndGrace(config.windowSize(), config.grace()))
                .aggregate(
                        WindowAccumulator::empty,
                        (key, event, acc) -> acc.add(ObservationMapper.toObservation(event)),
                        Materialized.<String, WindowAccumulator, WindowStore<Bytes, byte[]>>as(AGGREGATE_STORE)
                                .withKeySerde(Serdes.String())
                                .withValueSerde(new WindowAccumulatorSerde()))
                // Emit only when the window AND its grace period have closed. Without this, every
                // late event re-emits the window and a downstream consumer sees a stream of
                // revisions instead of one answer. The cost: output waits for stream time to
                // advance, so a quiet partition holds its last window open.
                .suppress(Suppressed.untilWindowCloses(Suppressed.BufferConfig.unbounded())
                        .withName("close-windows"))
                .toStream()
                .flatMap((windowed, acc) -> toAggregates(windowed, acc, clock), Named.as("to-aggregates"));
```

When I talk about this I say that `Suppressed.BufferConfig.unbounded()` is a memory risk I have not measured, and that a quiet partition holds its last window open because suppression waits for stream time to advance, which the ADR states as a cost.

### 🔴 Senior

**Q:** The schema-evolution gate says BACKWARD compatible. Is that enough to deploy a schema change safely?

**A:** No, and I want to be precise about what the gate proves. At build time `SchemaCompatibilityTest` checks that the current schema, as reader, can read data written with a frozen baseline schema, and it fails the pull request that adds a field without a default, renames a field or narrows a type; three fixtures prove it rejects, and a fourth proves an optional field with a default passes. At runtime, however, the codec builds both the writer and the reader from the same generated class, and its own javadoc says it does not resolve evolution across versions because that is what a Schema Registry would add. My reasoning, which I did not test with a mixed-version run, is that Avro binary carries no field names and no schema id, so a consumer built from schema v1 reading bytes written from v2, or the reverse, will misparse or fail to decode. A decode failure in the processor would send the record to the dead-letter topic, but a misparse that happens to decode would not, and I have not tested which one occurs, so the rollout window is a data-loss risk I cannot size. ADR-0005 also admits that the consumers-first deploy order is not enforced by anything, and the ADR text that says a registry arrives later is not true of the code today. The measured benefit of Avro is real: a heartbeat is 134 bytes against about 409 as JSON, recorded in the repo from my own measurement.


**Source:** `streampulse/libs/contracts/src/test/java/com/streampulse/contracts/SchemaCompatibilityTest.java:150-162`

```java
        @ParameterizedTest(name = "{0} is correctly REJECTED")
        @ValueSource(strings = {"AddedRequiredField", "RenamedField", "NarrowedType"})
        void breakingChangesAreRejected(String fixture) throws IOException {
            Schema breaking = parseResource("incompatible/" + fixture + ".avsc");
            Schema baseline = parseResource("baseline/TelemetryEvent.avsc");

            SchemaPairCompatibility result = check(breaking, baseline);

            assertThat(isCompatible(result))
                    .as("%s SHOULD be rejected but the gate accepted it — the gate is broken", fixture)
                    .isFalse();
            assertThat(result.getResult().getIncompatibilities()).isNotEmpty();
        }
```


**Source:** `streampulse/libs/contracts/src/main/java/com/streampulse/contracts/codec/AvroBinaryCodec.java:17-19`

```java
 * Raw Avro binary, no schema-registry framing: the topic carries exactly the bytes of one
 * record. Writer and reader schema are the same class, so this does not resolve schema
 * evolution across versions; that is what Schema Registry would add.
```

**Follow-up they will ask:** What would you do to make a breaking change safe without a registry?

**A:** I would use the mechanism ADR-0005 already names: a new topic version such as `telemetry.raw.v2`, with producers dual-writing and consumers migrating at their own pace until `v1` is idle. For compatible changes I would either add Schema Registry framing, so the writer schema travels with each record, or give the codec an explicit writer-schema argument and a version marker in a header. The trade-off is operating a registry or a header convention in return for rolling deploys that do not drop records. I have not built either, and I would say so in the interview rather than claim the gate alone makes deploys safe.

## Phase 5 — Reliability patterns in Java (idempotency, outbox with Debezium, poison records, retries)

> The delivery-semantics argument, the Redis claim, the outbox and the Debezium connector are explained in module 04 (`modules/04-event-driven-reliability.md`). This phase shows the Java mechanics and does not repeat that argument.

### 🟢 Beginner

**Q:** Where does idempotency show up in the Java code?

**A:** It shows up at three places. The client generates the `EventId`, validated in a record, so a retry carries the same id. The gateway claims that id atomically with Redis `setIfAbsent` before publishing, and releases the claim if the publish fails, so a client's retry is not mistaken for a duplicate. The sink writer uses an `INSERT ... ON CONFLICT DO UPDATE` keyed by the aggregate's identity, so a redelivered record changes nothing. Module 04 argues why each of the three is needed.

**Q:** Why do you release a permit in a `finally` block, and why restore the interrupt flag?

**A:** A `finally` block runs whether the `try` block returned or threw, so releasing the `Semaphore` permit there means a failure can never leak capacity. A leaked permit is a permanent reduction in throughput that shows up only as rising latency days later. When I catch `InterruptedException`, the thread's interrupt status has been cleared, so I call `Thread.currentThread().interrupt()` to restore it, otherwise code further up cannot tell the thread was asked to stop. During shutdown that is the signal I most need to preserve.

### 🟡 Intermediate

**Q:** How does the Java code stop an outbox row being written outside a transaction?

**A:** The port `ConfigChangeOutbox` is implemented by `JdbcConfigChangeOutbox.append`, annotated with `@Transactional(propagation = Propagation.MANDATORY)`. With MANDATORY, a call made without an active transaction throws instead of starting one, whereas REQUIRES_NEW would let the row commit on its own and outlive a rolled-back change. `ChangeRecorder` is called by each service inside its own transaction after the entity is saved, so the version in the announcement is the new one. `OutboxAtomicityIT` pins both directions against a real Postgres: a rolled-back change leaves no outbox row, and appending outside a transaction raises `IllegalTransactionStateException`.


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


**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/lab/TransactionBehaviourIT.java:182-190`

```java
    @DisplayName("a checked exception COMMITS by default; rollbackFor makes it roll back")
    void checkedExceptionCommitsByDefault() {
        assertThatThrownBy(() -> probe.insertThenThrowChecked("default")).hasMessage("checked failure");
        assertThat(rowExists("default")).as("committed despite the exception").isTrue();

        assertThatThrownBy(() -> probe.insertThenThrowCheckedWithRollbackFor("with-rollbackFor"))
                .hasMessage("checked failure");
        assertThat(rowExists("with-rollbackFor")).isFalse();
    }
```

The second snippet is the lab test that answers the checked-exception question with evidence: the checked failure committed the row, and `rollbackFor` rolled it back.

### 🔴 Senior

**Q:** How does the sink separate a poison record from an outage, and where is that weakest?

**A:** The listener decodes first and dead-letters anything undecodable or that the store would reject on every attempt. For the rest, `BatchWriter` retries the batch up to the configured attempts with doubling backoff, then writes the records one at a time: if some succeed the store is up and the failures are poison, so they are dead-lettered, and if none succeed it cannot tell a bad record from a dead store, so it fails them all and lets the listener redeliver. The Spring error handler never skips: its recoverer throws, and every exception is retried with capped exponential backoff and no attempt limit, so an outage is waited out. The config values are targets, not measurements: 200 rows or 100 ms per batch, queue 2,000, three flush attempts at 50 ms, and `max.poll.interval.ms` of 300,000 with a comment that it must exceed the poll budget plus the longest backoff. The weak spots are that a single poison record alone in a batch looks like an outage, that a failing dead-letter publish holds back the acknowledgement (deliberately, since skipping would lose the record), and that the alert engine's rule loader makes the opposite choice by logging and skipping a rule that fails to apply. I did not run these integration tests today, and their injected failures are exceptions, not killed processes.


**Source:** `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java:255-280`

```java
    /**
     * One record at a time. If some succeed the store is up, so the ones that failed are the
     * faulty records. If none succeed we cannot tell a bad record from a dead store, and dead-
     * lettering healthy records because the store was down would lose data: treat it as an outage.
     */
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

**Follow-up they will ask:** How do retries avoid making an incident worse in the gateway?

**A:** The publisher composes Retry outside CircuitBreaker outside TimeLimiter, so every attempt is counted by the breaker and a hanging call is cut by the limiter before the breaker sees it. The retry policy ignores three exception types: an open breaker, because retrying cannot succeed inside a sub-second budget; a timeout, because retrying a slow failure multiplies how long the batch holds an in-flight permit; and `IllegalArgumentException`, because a rejected batch fails identically. Everything else is retried up to three attempts with jittered exponential backoff. The honest limit is that "everything else" is a blacklist, and the file says a whitelist would be safer once both adapters' failure modes are mapped.


**Source:** `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/resilience/ResilientEventPublisher.java:145-151`

```java
    public static RetryConfig retryPolicy(int maxAttempts, IntervalFunction backoff) {
        return RetryConfig.custom()
                .maxAttempts(maxAttempts)
                .intervalFunction(backoff)
                .ignoreExceptions(
                        CallNotPermittedException.class, TimeoutException.class, IllegalArgumentException.class)
                .build();
```

## Phase 6 — Testing (JUnit, Testcontainers integration tests, architecture tests, what the CI runs)

### 🟢 Beginner

**Q:** How do you separate unit tests from integration tests?

**A:** By class name. Anything ending in `IT` is an integration test that starts containers, and everything else is a unit test that needs no Docker. The convention plugin makes the `test` task exclude `**/*IT.class`, registers an `integrationTest` task that includes only those classes, and makes `check` depend on `integrationTest`. As I understand Gradle's lifecycle, `build` runs `check`, which is why CI running `./gradlew build` also runs the integration tests; verify that in the current Gradle docs. By file name there are 149 test classes in `libs`, `services` and `functions`, of which 32 are `*IT`.

**Q:** What is the difference between a mock, a stub and a fake, and which do you prefer?

**A:** A stub returns canned answers, a mock also verifies the calls made on it, and a fake is a small working implementation such as an in-memory store. I prefer fakes because they let me assert on outcomes, such as what reached the publisher, instead of on how my code called a collaborator, and the version catalog comment says mocks are used sparingly. A search shows six test classes import Mockito, mostly controller tests, while the use-case tests use hand-written fakes like `FakePublisher` and `FakeIdempotencyStore`. The risk with fakes is that they can drift from the real adapter, which is why each adapter also has an integration test against a real container.

### 🟡 Intermediate

**Q:** How do your Testcontainers tests start real infrastructure and keep tests independent?

**A:** `PostgresIT` is an abstract `@SpringBootTest` base class that starts one Postgres 16 container per JVM in a static initializer, registers its URL with `@DynamicPropertySource`, and truncates every table before each test. That is fast because the container and the Spring context are reused, and it is a trade-off because tests share a database and rely on the truncate for isolation. The Postgres container is started with `wal_level=logical` so the Debezium test can share it. `OutboxAtomicityIT` extends it and proves the outbox rule: it creates a tenant inside a transaction, asserts the outbox row exists inside the transaction so the test is not vacuous, throws, and then asserts that both the tenant and the outbox row are gone.


**Source:** `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/support/PostgresIT.java:21-34`

```java
public abstract class PostgresIT {

    /** Shared so a CDC test can put Kafka Connect on the same network as the database. */
    protected static final Network NETWORK = Network.newNetwork();

    /** wal_level=logical and a replication slot are what Debezium needs; the other tests ignore them. */
    protected static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine")
            .withNetwork(NETWORK)
            .withNetworkAliases("postgres")
            .withCommand("postgres", "-c", "wal_level=logical", "-c", "max_replication_slots=4");

    static {
        POSTGRES.start();
    }
```

**Illustrative (not from the repo):** a unit test with an injected `Clock`, the pattern `EventValidator` uses for its future-skew rule.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class FutureSkewTest {

    static boolean tooFarInFuture(Instant occurredAt, Clock clock, Duration maxSkew) {
        return occurredAt.isAfter(clock.instant().plus(maxSkew));
    }

    private static final Clock NOW = Clock.fixed(Instant.parse("2026-01-15T12:00:00Z"), ZoneOffset.UTC);

    @Test
    void acceptsAnEventInsideTheSkew() {
        assertThat(tooFarInFuture(NOW.instant().plusSeconds(299), NOW, Duration.ofMinutes(5))).isFalse();
    }

    @Test
    void rejectsAnEventBeyondTheSkew() {
        assertThat(tooFarInFuture(NOW.instant().plusSeconds(301), NOW, Duration.ofMinutes(5))).isTrue();
    }
}
```

I compiled this with the cached JUnit 5.12.2 and AssertJ 3.27.3 jars and ran it through the JUnit launcher: two tests found, two succeeded, none failed. I use it to say that time is a dependency, so I inject a `Clock` and a fixed instant makes the test deterministic.

**Q:** How do you test a Kafka Streams topology without a broker?

**A:** `TelemetryTopologyTest` builds the real topology with `TopologyTestDriver`, which runs it in memory, pipes bytes into the input topic and reads the output and dead-letter topics. The class comment explains the subtlety that makes these tests honest: a window closes only when stream time advances, so most tests pipe a later "tick" record, and one test asserts that without the tick nothing is emitted. I set the state-store cache to zero, so the test asserts only what the topology promises and not commit timing. The topology is a pure function of its arguments with an injected `Clock`, which is what makes this possible.


**Source:** `streampulse/services/stream-processor/src/test/java/com/streampulse/processor/adapter/streams/TelemetryTopologyTest.java:74-86`

```java
        var props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "telemetry-topology-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:1234");
        props.put(StreamsConfig.STATE_DIR_CONFIG, stateDir.toString());
        // No record cache: with one, a window's updates are held until the next commit and
        // the test would assert on timing the topology does not promise.
        props.put(StreamsConfig.STATESTORE_CACHE_MAX_BYTES_CONFIG, 0);

        driver = new TopologyTestDriver(TelemetryTopology.build(config, validator, CLOCK, metrics), props);
        input = driver.createInputTopic(RAW, new StringSerializer(), new ByteArraySerializer());
        aggregates = driver.createOutputTopic(AGG, new StringDeserializer(), new ByteArrayDeserializer());
        deadLetters = driver.createOutputTopic(DLT, new StringDeserializer(), new ByteArrayDeserializer());
    }
```

### 🔴 Senior

**Q:** What does your CI run, and what does it not run?

**A:** The workflow runs on pushes to `main` and on pull requests, with a 20 minute timeout on `ubuntu-latest`. It sets up JDK 21 and Gradle, runs `./gradlew spotlessCheck`, then `./gradlew build --no-daemon`, which includes the integration tests through `check`, and it uploads test and coverage reports. Docker is needed for the `*IT` classes and GitHub's Ubuntu runners include it as far as I know; verify that, and note that I have not looked at a CI run's output. What it does not run is the React tests, Terraform validation, the Python checkers under `scripts/`, image builds and any load test, and Jacoco produces a report but I found no coverage threshold. One detail I derived from reading: the uploaded test report path is `build/reports/tests/test/`, which is the unit-test task's directory, so a failing integration test's HTML report is not uploaded, although the console output carries the full exception because the convention sets `exceptionFormat = FULL`. For numbers, I ran 55 tests today with 0 failures, and the repo's own record says control-plane had 102 tests, alert-engine 191, activity-feed 165 and mcp-server 87 with no failures in earlier runs, all on one machine.


**Source:** `streampulse/.github/workflows/ci.yml:45-49`

```yaml
      - name: Verify formatting
        run: ./gradlew spotlessCheck

      - name: Build and test
        run: ./gradlew build --no-daemon
```


**Source:** `streampulse/build-logic/src/main/kotlin/streampulse.java-conventions.gradle.kts:224-238`

```kotlin
val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs *IT classes (start containers; needs Docker)."
    group = "verification"
    testClassesDirs = testSourceSet.get().output.classesDirs
    classpath = testSourceSet.get().runtimeClasspath
    include("**/*IT.class")
    // Gradle 9 fails a Test task that discovers nothing. libs:platform and libs:contracts
    // have no *IT classes, and that is correct, not an error.
    failOnNoDiscoveredTests = false
    shouldRunAfter(tasks.named("test"))
}

tasks.named("check") {
    dependsOn(integrationTest)
}
```

**Follow-up they will ask:** What can a `TopologyTestDriver` test not prove, and how do you cover that?

**A:** It cannot prove rebalancing, real transactions under `exactly_once_v2`, broker failures or offset commits, because there is no broker. The repo covers part of that with `StreamProcessorIT` and `StreamProcessorRecoveryIT` against containers, and the sink has `NoLossNoDoubleCountIT` and `PoisonRecordIT`; I did not run them today. A separate limit is that all injected failures are exceptions in the same JVM, not a killed process or a partitioned network. The repo's own resilience notes record that a `kill -9` of the processor mid-window dropped events as expired-window records, which is the kind of failure these tests do not model.

## Phase 7 — Concurrency, the JVM and operating it (Java 21, shared state, Micrometer, health checks)

### 🟢 Beginner

**Q:** What is a virtual thread, and where do you use one?

**A:** A virtual thread is a lightweight thread scheduled by the JVM onto a small pool of carrier threads, final in Java 21, and when it blocks on I/O it unmounts so it costs memory instead of an operating-system thread. I enable `spring.threads.virtual.enabled` in the ingest gateway, alert engine and activity feed, because their requests block on Kafka, Redis, Postgres or HTTP. The ingest gRPC server uses `Executors.newVirtualThreadPerTaskExecutor()`, and the alert engine's SSE writers use `Thread.ofVirtual()`. The sink writer and stream processor do not enable virtual threads, and the `spring-service` convention sets the property only for test tasks, so I must not say every service runs on them in production.

**Q:** What is the difference between `volatile`, `synchronized` and a `ReentrantLock`?

**A:** `volatile` guarantees visibility and ordering of a single variable across threads but not atomic read-modify-write. `synchronized` gives mutual exclusion and visibility with a block-scoped monitor, and `ReentrantLock` offers the same exclusion with explicit `lock` and `unlock`, timeouts and fairness options. I use `volatile` for flags such as `closed` in `BatchWriter` and `running` in lifecycle beans, and `ReentrantLock` where a lock is held around blocking work. On Java 21 a virtual thread that blocks inside `synchronized` pins its carrier, so I avoid that pattern; a later JDK is reported to remove the pinning, and I believe it is JDK 24, but verify in the current docs.

**Q:** What is the difference between a liveness and a readiness probe?

**A:** Liveness asks whether the process is broken beyond recovery, and the only cure Kubernetes has is a restart, while readiness asks whether it should receive traffic right now. In the gateway, the sink writer and the stream processor I put only `livenessState` in the liveness group, because putting Redis there would restart every pod at once when Redis blips, and the gateway fails open on Redis anyway. The stream processor adds a `streamsState` indicator to readiness only, and it counts a rebalance as up so a rolling deploy does not remove every pod at once. During shutdown the gateway flips readiness to refusing traffic, not liveness, so Kubernetes drains the pod instead of restarting it.

### 🟡 Intermediate

**Q:** How is `BatchWriter` thread-safe, and why that lock?

**A:** One dedicated platform thread, `batch-flusher`, drains a bounded `ArrayBlockingQueue`, and any number of listener threads call `submit`. A `volatile boolean closed` plus a `ReentrantReadWriteLock` make "is it open?" and "enqueue" one step with respect to `close()`: submitters take the shared read lock, and `close()` takes the write lock only to set the flag. Without it, `submit` could see the writer open, `close()` could set the flag and let the flusher exit on an empty queue, and `submit` could then enqueue a record nothing would ever write. I chose a read-write lock over `synchronized` because `submit` blocks in `offer`, so the exclusion has to survive a blocking call; the trade-off is that `close()` waits for in-flight offers, bounded by the offer timeout.


**Source:** `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java:125-139`

```java
        lock.readLock().lock();
        try {
            if (closed) {
                return rejected(SubmissionRejectedException.Reason.CLOSED);
            }
            if (!queue.offer(new Pending<>(value, future), offerTimeout.toNanos(), TimeUnit.NANOSECONDS)) {
                return rejected(SubmissionRejectedException.Reason.BUFFER_FULL);
            }
            return future;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return rejected(SubmissionRejectedException.Reason.INTERRUPTED);
        } finally {
            lock.readLock().unlock();
        }
```

**Q:** How do you share read-mostly state without locking the hot path?

**A:** `RuleBook` holds the alert rules in a `volatile` field that points to an immutable snapshot. Readers on the evaluation path read the field once and use that snapshot with no lock, while writers take a `ReentrantLock`, build a new snapshot from copies of the maps, and publish it with one volatile write. A write replaces one tenant's rules and rebuilds that tenant's dependency graph, so a cyclic rule set throws before the book changes. The cost is allocation per write, which is fine because rule changes are rare and reads happen for every observation.


**Source:** `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/RuleBook.java:55-56`

```java
    private final ReentrantLock writeLock = new ReentrantLock();
    private volatile Snapshot snapshot = new Snapshot(Map.of(), Map.of());
```


**Source:** `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/RuleBook.java:113-121`

```java
    public List<AlertRule> rulesFor(Observation observation) {
        TenantRules tenant = snapshot.tenants().get(observation.tenantId());
        if (tenant == null) {
            return List.of();
        }
        return tenant.byMetric().getOrDefault(observation.metric(), List.of()).stream()
                .filter(rule -> rule.matches(observation))
                .toList();
    }
```

This is copy-on-write with a volatile reference, and the same idea as `List.copyOf` in a compact constructor: build the new immutable value, then publish it.

### 🔴 Senior

**Q:** How do you operate this under load and at shutdown, and what is unproven?

**A:** Concurrency is bounded at the edges: a fair `Semaphore` of 64 in-flight batches with a 250 ms permit wait returns 503 instead of queueing, the sink's buffer holds 2,000 records with a 1 s offer timeout, and the query API's blocking calls run on a fixed pool with a bounded queue that rejects when full. Shutdown is ordered with `SmartLifecycle` phases: readiness flips first, the HTTP connector stops, the gateway then waits for permits to return up to a 20 s drain timeout, and the sink closes its writer after the Kafka listener container stops; the phase numbers in the class comments are mine, and I did not verify Boot's internal phase values. The measured numbers are from the repo's own record on one Apple M2 Pro with a single broker: ingest p99 68.7 ms at 1,500 events per second, clean at 40,000 events per second and 503s from 45,000, with the load generator sharing the CPU, so I would not quote either as capacity. Heap moved between 45.5 and 313 MiB with 34 to 35 threads while refusing 105,800 events. What is unproven is virtual-thread pinning: the ADR says to measure with `-Djdk.tracePinnedThreads`, and the interview notes record that the measurement has not been done, so I do not claim the pinning risk is absent or present. I also have not measured drain time under a real SIGTERM.


**Source:** `streampulse/services/stream-processor/src/main/java/com/streampulse/processor/config/StreamsStateHealthIndicator.java:26-31`

```java
    @Override
    public Health health() {
        KafkaStreams.State current = state.get();
        Health.Builder builder = current.isRunningOrRebalancing() ? Health.up() : Health.down();
        return builder.withDetail("state", current.name()).build();
    }
```

**Follow-up they will ask:** Why does `AlertProcessor` use a `ReentrantLock` held across evaluation and delivery?

**A:** Two threads, the aggregate listener and the absence sweeper, both evaluate and then drain an outbox to delivery channels, and one lock across the three steps keeps changes entering the outbox in the order the engine produced them. The drain calls channels that block on the network, so `ReentrantLock` is the safer primitive on Java 21 than `synchronized`, which would pin a virtual thread's carrier. The honest caveat is that the alert engine's Kafka consumer is a platform thread, so the pinning argument is defensive there, and a single lock serialises all evaluation, which caps throughput at one thread's worth. I have not measured that ceiling. A related unproven point is that `BatchWriter.flusher` is a plain non-volatile field assigned after construction and read in `close()`; I believe Spring's singleton registration publishes it safely, but I have not verified it.


**Source:** `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/application/AlertProcessor.java:48-56`

```java
    private void run(java.util.function.Supplier<List<Alert>> step) {
        lock.lock();
        try {
            outbox.add(step.get());
            outbox.drain();
        } finally {
            lock.unlock();
        }
    }
```

## Code reference index

| path:lines | what it shows |
|---|---|
| `streampulse/settings.gradle.kts:70-81` | The twelve included projects, libraries first |
| `streampulse/build-logic/src/main/kotlin/streampulse.java-conventions.gradle.kts:224-238` | `test` excludes `*IT`, `integrationTest` includes them, `check` depends on it |
| `streampulse/build-logic/src/main/kotlin/streampulse.spring-service.gradle.kts:61-63` | Virtual threads property set for test tasks only |
| `streampulse/libs/platform/src/test/java/com/streampulse/platform/ArchitectureRulesTest.java:86-100` | Domain free of framework imports (platform scope only) |
| `streampulse/services/ingest-gateway/src/test/java/com/streampulse/ingest/IngestArchitectureRulesTest.java:84-101` | Adapters depend on the port, not on `IngestService` |
| `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/ControlPlaneArchitectureRulesTest.java:92-104` | The clock rule that only two modules enforce |
| `streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java:46-69` | Record with a validating, normalising compact constructor |
| `streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/TenantId.java:66-88` | Trim, lowercase with `Locale.ROOT`, length and regex checks |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/domain/IngestCommand.java:34-46` | Tenant as a separate argument, defensive `List.copyOf` |
| `streampulse/services/stream-processor/src/main/java/com/streampulse/processor/domain/Validation.java:6-19` | Sealed result type with two records |
| `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/evaluator/Evaluators.java:29-35` | Exhaustive switch over a sealed `Condition` |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/application/IngestService.java:171-186` | Compensating release on publish failure |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestController.java:53-68` | Thin controller calling the use case port |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/config/IngestConfig.java:108-124` | Composition root selecting the Kafka publisher |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/in/rest/IngestExceptionHandler.java:49-72` | Problem Details with `Retry-After` for 503 |
| `streampulse/api/openapi/ingest-v1.yaml:70-74` | The documented 413 that the code does not return |
| `streampulse/services/control-plane/src/main/java/com/streampulse/controlplane/application/TenantService.java:27-38` | `@Transactional` service that records a change in the same transaction |
| `streampulse/services/ingest-gateway/src/main/resources/application.yml:70-90` | Producer idempotence, `acks=all`, batching and timeouts |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/kafka/KafkaEventPublisher.java:66-86` | Session id as key, `occurredAt` as record timestamp |
| `streampulse/libs/contracts/src/main/java/com/streampulse/contracts/codec/AvroBinaryCodec.java:17-19` | Raw Avro, no evolution resolution |
| `streampulse/libs/contracts/src/main/java/com/streampulse/contracts/codec/AvroBinaryCodec.java:59-79` | Decode with trailing-byte check and one exception type |
| `streampulse/services/stream-processor/src/main/java/com/streampulse/processor/adapter/streams/TelemetryTopology.java:98-123` | Dedup, re-key, window, suppress, flatMap |
| `streampulse/services/stream-processor/src/main/resources/application.yml:18` | `processing.guarantee: exactly_once_v2` |
| `streampulse/api/asyncapi/streampulse-topics.yaml:25-53` | Key, partition count and rejected alternatives for the raw topic |
| `streampulse/docker/compose.yml:108-114` | Topic creation with partitions and the compacted config topic |
| `streampulse/services/sink-writer/src/main/resources/application.yml:36-55` | Manual ack, `read_committed`, batch listener |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/adapter/in/kafka/AggregateBatchListener.java:63-81` | Decode, submit, wait for all, then acknowledge |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java:125-139` | Read-write lock around the open check and enqueue |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/application/batch/BatchWriter.java:255-280` | Isolation: poison versus outage |
| `streampulse/services/sink-writer/src/main/java/com/streampulse/sink/config/SinkConfig.java:145-166` | Error handler that never skips and never gives up |
| `streampulse/services/control-plane/src/main/java/com/streampulse/controlplane/adapter/out/outbox/JdbcConfigChangeOutbox.java:31-47` | `Propagation.MANDATORY` outbox append |
| `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/lab/TransactionBehaviourIT.java:182-190` | Checked exception commits by default |
| `streampulse/docker/debezium/outbox-connector.json:14-34` | EventRouter configuration, key and tombstone settings |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/adapter/out/resilience/ResilientEventPublisher.java:145-151` | Retry policy with three ignored exception types |
| `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/support/PostgresIT.java:21-34` | One Postgres per JVM, `wal_level=logical` |
| `streampulse/services/control-plane/src/test/java/com/streampulse/controlplane/OutboxAtomicityIT.java:81-97` | Rollback leaves no outbox row |
| `streampulse/services/stream-processor/src/test/java/com/streampulse/processor/adapter/streams/TelemetryTopologyTest.java:74-86` | `TopologyTestDriver` setup with zero cache |
| `streampulse/libs/contracts/src/test/java/com/streampulse/contracts/SchemaCompatibilityTest.java:150-162` | Gate proof: breaking fixtures are rejected |
| `streampulse/.github/workflows/ci.yml:45-49` | `spotlessCheck`, `build`, report upload paths |
| `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/RuleBook.java:55-56` | Writer lock and volatile snapshot field |
| `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/domain/RuleBook.java:113-121` | Lock-free read of the snapshot |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/config/MicrometerIngestMetrics.java:38-47` | Counters registered once, no dynamic tags |
| `streampulse/services/stream-processor/src/main/java/com/streampulse/processor/config/StreamsStateHealthIndicator.java:26-31` | Readiness treats rebalancing as up |
| `streampulse/services/ingest-gateway/src/main/java/com/streampulse/ingest/lifecycle/IngestDrainLifecycle.java:97-112` | Readiness flip, bounded drain, callback in `finally` |
| `streampulse/services/alert-engine/src/main/java/com/streampulse/alert/application/AlertProcessor.java:48-56` | One lock across evaluate, record and deliver |
| `streampulse/docs/interview/06-numbers.md` | Measured, target and assumed numbers with sources |
| `streampulse/docs/adr/0012-kafka-streams-primary.md` | Exactly-once scope and the raw-Avro, no-registry decision |
| `streampulse/docs/adr/0006-virtual-threads-over-webflux.md` | Why MVC on virtual threads, and the pinning caveat |

## Self-check

1. Why do the architecture tests live in each module and not in `libs/platform`? Because ArchUnit scans the module's own test classpath, and `libs/platform` depends on no service, so it cannot see their classes.
2. What does `Propagation.MANDATORY` on `JdbcConfigChangeOutbox.append` change compared with `REQUIRES_NEW`? It throws when no transaction is active instead of committing the row on its own, so an announcement cannot outlive a rolled-back change.
3. Why is the BACKWARD gate not enough for a runtime rollout? Because the codec uses the same generated class as writer and reader schema, so it does not resolve versions, and nothing enforces consumers-first deployment.
4. Why does `BatchWriter` use a read-write lock and a `volatile` flag together? So that checking "open" and enqueueing are one step with respect to `close()`, without `synchronized` pinning a virtual thread while `offer` blocks.
5. What does the CI not upload when an integration test fails? The integration test HTML report, because the upload path is the unit-test task's report directory; the console exception output still appears.

## What not to claim

- Do not say all services run on virtual threads in production; only the gateway, alert engine and activity feed enable them in `application.yml`, and the convention plugin sets the property for test tasks only.
- Do not say the architecture rules are uniform or proven; the sets differ per module, `libs/platform` cannot see service classes, the clock rule exists in two modules only, and I have not mutated a rule to see it fail.
- Do not say the schema gate makes a rollout safe; it is a build-time check, the codec does not resolve schema versions, and I have not run a mixed-version test.
- Do not say the pipeline computes payload-driven metrics; `AvroEventMapper` sets the payload to null and the processor derives only distinct sessions and an error ratio from the event type.
- Do not say the OpenAPI document matches the code exactly; it lists a 413 for an oversized batch while the code returns 400, and `max-batch-size` in configuration is bound but never read.
- Do not say the Kinesis path is the default; `streampulse.backbone` defaults to Kafka (ADR-0012), even though a comment in the gateway's `build.gradle.kts` still says Kinesis is the default.
- Do not say the ADR statement that a Schema Registry arrives in a later phase is true of the code; ADR-0012 and the codec record that there is none.
- Do not claim the `IngestDrainLifecycle` double registration (`@Component` plus `@Bean`) is verified safe; I believe the `@Bean` definition replaces the scanned one, and the fix is to remove the annotation.
- Do not quote the throughput, latency or heap numbers without the conditions: one Apple M2 Pro, one broker, replication factor 1, and the load generator sharing the CPU.
- Do not say virtual-thread pinning was measured, or that JEP 491 applies to the JDK I ship; both are marked verify, and the measurement task was not done.
- Do not claim any `*IT` class passed today; I ran 55 unit and architecture tests in one offline Gradle invocation and none of the Testcontainers tests.
- Do not claim production use; this is a learning and portfolio system, its scenarios are labelled fictional in `CLAUDE.md`, and some commits are co-authored with Claude, so I defend each line from the code.
