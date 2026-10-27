# Scenarios 06 — GraphQL & API design

Real-time situations for [module 06](../06-graphql-and-api-design.md). Each one is a customer or partner problem an FDE (Forward Deployed Engineer, the person who makes the product work inside one customer's tool estate) meets when exposing or consuming an API.

Lanes: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only. The GraphQL service is my own build in `GolangExercise/offline-sync-app` (gqlgen, a hand-written DataLoader), run only on a local synthetic setup and never deployed. Every number in a **Situation** is an invented example. Numbers marked "recorded" come from tests or from `docs/graphql.md`, on local synthetic data. Relative links reach sibling repos, so they resolve only with the same checkout layout as my laptop. I do not paste Couchbase monorepo code.

Ladder: 🟢 scenarios 1-2, 🟡 scenarios 3-4, 🔴 scenarios 5-6.

---

## Scenario 1 — The list query takes 4 seconds 🟢

**Situation.** Wednesday 16:00. The customer's portal page "locations with their assessments and photos" takes 4.2 s (example) for a page of 50 locations. In the demo with 5 rows it took 300 ms. A slow-query log excerpt (example) shows 200 near-identical statements like `SELECT ... FROM site_assessments WHERE location_id = $1`.

**Level.** 🟢 Beginner.

**What's being tested.** Recognizing an N+1 (one query for the list plus one per parent plus one per child) and knowing the standard fix, a per-request DataLoader.

**Clarifying questions to ask first.**
1. Is it slow for every request or only for large pages? Slowness that scales with page size points to N+1.
2. How many database statements does one request issue?
3. Is the data loader (or any batching) already in place, and is its cache per request?
4. Which fields does the client actually request? Removing a nested field from the query is a quick experiment.
5. Is the database itself slow, or is it many fast queries?

**Flow of control and data.**

```
client --POST /graphql--> list resolver: 1 query -> 50 locations
   naive:  each Location.siteAssessments -> 1 query (50)   each assessment.photos -> 1 query (150)   total 201
   loader: 50 resolvers Load(id) in a 2 ms window --> 1 batched query WHERE location_id = ANY($1)   total 3
```

**Diagnosis steps.**
1. Count statements per request: enable statement logging or look at `pg_stat_statements` calls for the child-table queries. Expect 1 + 50 + 150 = 201 for 50 locations with 3 assessments each and 2 photos each.
2. Per-statement time: if each is 1-2 ms, the total is a round-trip problem, not a slow query.
3. Trace each resolver: the time is spread across many tiny child resolvers.
4. Read the resolver for the slow field: does it call the store with one id (`[]uuid.UUID{obj.ID}`), or the loader?
5. Re-run the same query with the nested field removed. If latency collapses, the nesting is the cause.

**Fix now vs fix properly.**
- Now: batch the hot field with one `WHERE ... = ANY($1)` query, or lower the page size as a stopgap.
- Properly: a DataLoader per request, built in request scope, so every nesting level costs one query. The cache is per request and never shared across users.

**How you'd test it.** A call-count assertion on a fake store: `TestNPlusOne_BatchedIssuesConstantNumberOfStoreCalls` expects 3 store calls, and `TestNPlusOne_NaiveResolversIssueOnePlusNPlusM` shows the naive shape issues 201. `TestIntegration_NestedQueryIssuesConstantNumberOfSQLStatements` repeats it on real Postgres. `TestNPlusOne_LoaderCacheIsPerRequest` proves the cache does not leak across requests.

**Spoken answer (60-90 seconds).**
"Slow that grows with page size and made of many tiny queries is the signature of N+1. A list resolver fetches 50 parents with one query, then each parent's child resolver issues its own query, and each child's children do the same, so 50 locations with 3 assessments and 2 photos each cost 1 plus 50 plus 150, which is 201 statements. I would confirm by counting statements per request and checking that each one is fast but there are hundreds. The fix is a DataLoader: it collects the keys requested by many resolvers inside a short window, in my build 2 milliseconds, and fetches them with one query using ANY of the ids, so the same request costs 3 statements. The loader has to be created per request, because a cache shared across requests would leak one user's data to another and would never invalidate. I assert the call counts in tests, 3 batched versus 201 naive. What I did not measure is the latency cost of the 2 millisecond window, and I did not benchmark my loader against a library like dataloadgen."

**Follow-ups the interviewer will ask.**
- Why not a SQL join? A join over three levels multiplies rows and breaks pagination of the parent list; batching keeps one query per level.
- What if a batch fails? The error is stored on the batch and returned to every waiter, which gives one failed query and many error entries.
- Why per-request scope? No cross-user leakage and no stale cache.

**Tie to your code.** [L] DataLoader: [dataloader.go](../../../../../GolangExercise/offline-sync-app/internal/graph/dataloader.go). Call-count tests: [nplusone_test.go](../../../../../GolangExercise/offline-sync-app/internal/graph/nplusone_test.go).

---

## Scenario 2 — Offset pagination skips rows during a sync 🟢

**Situation.** Friday 06:00. A partner's nightly job pulls 5,000 records through `?offset=N&limit=100` while our field team adds records (example). Their reconciliation says 7 records are missing and 4 appear twice (example). Re-running the job gives different missing ids.

**Level.** 🟢 Beginner.

**What's being tested.** Why offset pagination is unstable under concurrent writes and why keyset (cursor) pagination fixes it.

**Clarifying questions to ask first.**
1. What is the sort order of the list, and is it unique? Ties without a tiebreaker give unstable pages.
2. Are rows inserted or updated while the partner walks the pages?
3. Does the partner pull everything each night or only changes since last time?
4. Can the partner deduplicate on id, and is applying a row twice safe for them?
5. How big does the table get, and how slow are deep offsets?

**Flow of control and data.**

```
walk by offset:   page 1 = rows 1..100
   a row is inserted before position 100
   page 2 = rows 101..200  --> the old row 100 is now row 101: DUPLICATE (or a delete shifts rows: SKIP)
walk by keyset:   page 1 ends at (updated_at, id) = X
   page 2 = WHERE (updated_at, id) > X ORDER BY updated_at, id LIMIT 100   --> position-based, stable
```

**Diagnosis steps.**
1. Get the partner's request log: which offsets were requested and when.
2. Compare the id sets across two runs to see that the missing and duplicated ids cluster at page boundaries.
3. Check the writes during the run: insert timestamps inside the window.
4. Check the `ORDER BY`: many rows can share one `updated_at`, so without `id` as a tiebreaker rows at a page boundary can be lost or repeated.
5. Measure a deep-offset query time to show offset cost grows with depth.

**Fix now vs fix properly.**
- Now: tell the partner to re-run with an overlap and deduplicate by id, and make the id stable.
- Properly: keyset pagination on `(updated_at, id)` with an opaque cursor, an inclusive `updated_since` filter for incremental runs, and an at-least-once contract: a row updated mid-walk is delivered again, never skipped, and the consumer dedupes by id.

**How you'd test it.** `TestIntegration_KeysetPaginationBreaksTimestampTiesOnID` seeds groups of rows sharing one timestamp and pages by 7. `docs/graphql.md` records that a manual mutation run that dropped `id` from the comparison lost 15 of 50 rows. `TestIntegration_RowUpdatedMidWalkReappearsAndIsNeverSkipped` proves at-least-once, and `TestIntegration_UpdatedSinceUsesInclusiveLowerBound` proves the boundary.

**Spoken answer (60-90 seconds).**
"Offset pagination counts rows from the start on every request, so if a row is inserted before your offset while you are walking, everything shifts by one. You see one row twice, and with a delete you skip one. It is also slow at depth because the database has to walk past all the skipped rows. For a sync I would use keyset pagination: the cursor is the position of the last row, in my build the updated_at in microseconds and the row id, and the next page is a row comparison, updated_at and id greater than the cursor, ordered by the same two columns. The id is essential because many rows can share one timestamp, and in my mutation run dropping it lost 15 of 50 rows. A row updated mid-walk moves to the end, so it is delivered again rather than skipped, which means the consumer must deduplicate on id. That is at-least-once, not exactly-once, and a late commit with an older timestamp than the partner's checkpoint can still be missed, so I would pair it with an overlap window and a periodic full reconcile."

**Follow-ups the interviewer will ask.**
- Why is the cursor opaque? So the client treats it as a position token and the server can change its content.
- Is a base64 cursor secure? No, it is not signed; a client can forge it, but it only selects a position and a bad one returns `BAD_USER_INPUT`.
- Why no `totalCount`? A `COUNT(*)` per page is the expensive part of a feed that never needs it.

**Tie to your code.** [L] Cursor encode and decode: [cursor.go](../../../../../GolangExercise/offline-sync-app/internal/graph/cursor.go). Keyset SQL builder: [pgstore.go](../../../../../GolangExercise/offline-sync-app/internal/graph/pgstore.go). The offset-based REST endpoint in this story is hypothetical and was not built: [K].

---

## Scenario 3 — A partner sends a deeply nested query 🟡

**Situation.** Saturday 03:10. CPU on the GraphQL service sits at 90% and p99 latency has tripled for every client (example). A request log shows one partner client sending a 40 KB document that nests `siteAssessments { location { siteAssessments { location ... } } }` about 20 levels deep (example).

**Level.** 🟡 Intermediate.

**What's being tested.** Why GraphQL needs query-cost defense that REST routes do not, and which layered limits reject a hostile query before any resolver runs.

**Clarifying questions to ask first.**
1. Is the schema cyclic (a back-reference such as `SiteAssessment.location`)? A cyclic schema lets a client nest forever.
2. Which client or token sent it, and is it malicious or a buggy generated query?
3. Are introspection and persisted queries enabled or restricted?
4. What limits exist today: depth, field count, complexity, page size, timeout, per-client rate?
5. Is the document hitting the parser, the validator or the resolvers?

**Flow of control and data.**

```
client --> auth (401 before anything else) --> request scope (loaders)
   parser token limit 5000 --> depth <= 8 --> expanded fields <= 1000 --> complexity <= 10000
   --> page size <= 100 --> 10 s request timeout --> resolvers --> store
   a violation returns HTTP 422 before any store call
```

**Diagnosis steps.**
1. Request log: document size, operation name, client identity, and response status.
2. Resolver and database metrics: do the heavy requests reach the store, or are they rejected earlier?
3. Compute the depth and cost of the sample query. A 20-hop cycle has depth 42 in my recorded test, against a limit of 8.
4. Check for aliases and fragments: 10 aliases of a 1,200-cost page cost 12,000 and are rejected.
5. Check whether auth runs outermost, so unauthenticated traffic never allocates loaders.
6. Check whether the client stays under every limit yet floods valid queries, which only a rate limit can stop.

**Fix now vs fix properly.**
- Now: block or throttle that client at the gateway or WAF and lower limits temporarily.
- Properly: layered limits checked cheapest first (tokens, depth, field count, complexity, page size, timeout) with a memoized walk so a fragment bomb is rejected in linear time, plus per-client rate limits and a persisted-query allowlist. Per-client rate limiting and persisted queries are not built in my repo.

**How you'd test it.** `TestDepthLimit_RejectsAbusiveCyclicQuery`, `TestDepthLimit_AllowsDeepestLegitimateQuery`, `TestDepthLimit_BoundaryIsInclusive`, `TestMeasure_MemoisesFragmentsSoABombIsLinear`, `TestComplexityLimit_RejectsWideNestedPage` (first 100 costs 11,200, rejected) and `TestComplexityLimit_AllowsHalfSizedPageOfTheSameShape` (first 50 costs 5,600, accepted). Rejections assert zero store calls. I did not test the gqlparser validator itself against fragment bombs.

**Spoken answer (60-90 seconds).**
"In REST each route has a roughly known cost, but in GraphQL the client writes the query, and my schema is cyclic because an assessment points back to its location, so a client can nest as deep as it likes. I would first block that client at the gateway to stop the damage, then look at why the service did not reject the query itself. My service checks cheapest first: a parser token limit, then depth at most 8, then an expanded field count, then an estimated complexity of rows materialised at most 10,000, then a page size cap and a 10 second timeout. The depth and field walk is memoised so a fragment bomb is walked in linear time before gqlgen's own complexity walk would re-expand every spread. A violation returns 422 before any resolver or store call, and my tests assert zero store calls on rejection. What this does not stop is an authenticated client that stays under every limit and floods valid queries. That needs a per-client rate limit at the gateway and ideally persisted queries, and I have not built either."

**Follow-ups the interviewer will ask.**
- Why clamp `first` before multiplying cost? A huge value could overflow into a cheap negative number before the resolver rejects it.
- Why 422 and not 200? gqlgen's default would answer 200, which hides violations from gateways and monitoring.
- Is 10 assessments per location a fact? No, it is an estimate because nothing caps it; 10 photos per assessment is real because the upsert caps it.

**Tie to your code.** [L] Limits and complexity: [limits.go](../../../../../GolangExercise/offline-sync-app/internal/graph/limits.go). Handler order (auth outermost): [handler.go](../../../../../GolangExercise/offline-sync-app/internal/graph/handler.go). Tests: [safety_test.go](../../../../../GolangExercise/offline-sync-app/internal/graph/safety_test.go). Rate limiting and persisted queries: [K], not built.

---

## Scenario 4 — Photos show zero but every request returns 200 🟡

**Situation.** Tuesday 11:30. The customer's dashboard has shown photo counts of 0 for every location since 09:00 (example). The uptime monitor is green and the API returns HTTP 200 for every request (example). Server log (example): `graphql: resolver error at [locations edges 0 node siteAssessments 0 photos]: ...`.

**Level.** 🟡 Intermediate.

**What's being tested.** Partial results, nullability as a reliability contract, error masking, and why status-code monitoring misses GraphQL failures.

**Clarifying questions to ask first.**
1. Does the response contain an `errors[]` array alongside `data`? What `path` do the errors carry?
2. Is the failing field nullable in the schema, so one failure degrades one path?
3. Is the failure a single batch error repeated per field, or many independent failures?
4. What changed at 09:00: a deploy, a migration, a permission or a database change on the photos table?
5. How does the client treat `null` for `photos`: as zero, or as unknown?

**Flow of control and data.**

```
photos loader batch --> store error --> stored on the batch --> returned to EVERY waiting resolver
response: HTTP 200, data with photos = null, errors[] one entry per affected path
presentError: resolver error (has path, no code) --> logged server-side, client sees "internal error"
root list failure --> locations is non-null --> data = null, one masked error
```

**Diagnosis steps.**
1. Capture one full response body and read `errors[].path` and `errors[].extensions.code`.
2. Count server log lines from the presenter by path. One failing batch produces N errors, one per waiting field.
3. Check the photos batch query directly in the database with a sample id list to see the real error (permissions, timeout, missing column).
4. Compare the first failure time with deploy and migration times.
5. Check how the client renders a null photo list. A UI that shows `0` for null hides the incident.

**Fix now vs fix properly.**
- Now: fix the failing dependency and tell the customer the exact window.
- Properly: emit a counter from the error presenter labelled by path and code and alert on its rate, because HTTP status alone cannot see this. Make sure clients distinguish null (unknown) from an empty list. Keep child fields nullable so one failure degrades one path. In my repo the presenter only logs, with no metric, and there is no tracing.

**How you'd test it.** `TestPartialResults_FailingChildFieldKeepsSiblingsAndReportsPath` asserts 6 errors from one photos batch call, all masked, the response still 200, and a fake password seeded into the store error never appears in the response. `TestPartialResults_FailingStatsDoNotLoseTheLocation` and `TestRootFailureNullsDataAndReportsOneMaskedError` cover the other two shapes.

**Spoken answer (60-90 seconds).**
"In GraphQL a field-level failure is not a transport failure, so the HTTP status stays 200 and the error is in an errors array with a path. That is why a status-based monitor is green. In my service photos is nullable, so when the photos batch fails the client gets all the locations and assessments, photos as null, and one error entry per affected path; my test shows one failed batch produces six errors. I mask resolver errors, so the client sees a generic internal error and the real text, which might contain SQL or a hostname, stays in the server log. For this incident I would read one real response body, group the logged errors by path, run the photos batch query by hand to see the real cause, and line the first failure up against a deploy or migration. The longer-term fix is monitoring: emit a counter from the error presenter by path and code and alert on it. That is a design, not something I built, since today the presenter only logs. I would also check that the client does not render null as zero."

**Follow-ups the interviewer will ask.**
- Why is `Query.locations` non-null? If the root list fails there is nothing to return, so `data` becomes null with exactly one masked error.
- What if a resolver panics? gqlgen nulls the entire list when an element panics, so a resolver must return an error instead; the loader's timer goroutine recovers panics itself.
- Is the masking rule safe? It keys on path and code, so any resolver error someone tags with a code passes through; today only `BAD_USER_INPUT` is used that way.

**Tie to your code.** [L] Error presenter: [handler.go](../../../../../GolangExercise/offline-sync-app/internal/graph/handler.go). Tests: [safety_test.go](../../../../../GolangExercise/offline-sync-app/internal/graph/safety_test.go). Error-rate metric and alert: [K], not built.

---

## Scenario 5 — A partner's mirror never sees deletes and misses late rows 🔴

**Situation.** Monday 10:00. A partner's integration team reports that their mirror holds 140 locations we deleted weeks ago, and 3 rows never arrived despite "complete" syncs (example). They sync through the GraphQL feed with `updatedSince` and a stored watermark.

**Level.** 🔴 Senior.

**What's being tested.** Designing a sync contract for a partner: tombstones, versions, overlap, inclusive boundaries, and honesty about what the current schema cannot express.

**Clarifying questions to ask first.**
1. How does the partner walk the feed: cursor only, `updatedSince` from the max timestamp it saw, or both?
2. Does the API ever express a delete: a flag, a tombstone row, an event?
3. Is there a monotonic version, or only `updatedAt`?
4. Can rows be committed late with an older `updatedAt` than the partner's watermark (offline devices syncing a queued edit)?
5. What freshness and correctness does the partner need, and can they run a periodic full listing?

**Flow of control and data.**

```
partner: run N  -> pages by (updated_at, id), keeps max updated_at as watermark
partner: run N+1 -> updatedSince = watermark (inclusive >=) --> cursor pages
   delete in our DB --> row gone --> no row in any page --> mirror keeps it (silent)
   late commit with updated_at < watermark --> never returned --> missing row
repair: tombstones + version in the feed, overlap window, periodic full id reconcile
```

**Diagnosis steps.**
1. Confirm the feed's behavior for deletes: delete a test row and see whether any page ever mentions it. In my schema there is no `deletedAt` and no version field, so it cannot.
2. For the 3 missing rows, compare each row's `updated_at` and commit time with the partner's watermark at the time. An older timestamp than the watermark means a late commit.
3. Check that the partner uses `updatedSince` inclusively and restarts from the max timestamp, so boundary rows are re-read.
4. Check their overlap window; a poll that starts exactly at the watermark has none.
5. Compare the full id list on both sides to size the delete and missing sets.

**Fix now vs fix properly.**
- Now: send the partner a full id list for a one-off reconcile of the 140 and the 3.
- Properly: add a nullable `deletedAt` (soft delete that moves the row forward in the `(updated_at, id)` feed) and a monotonic `version`, document at-least-once delivery with consumer dedupe, recommend a start-earlier overlap, add tombstone retention, and run a periodic full reconcile. The current GraphQL schema has none of the first two, so this is design, not shipped.

**How you'd test it.** For the schema extension I would add a feed test that a soft-deleted row appears once with `deletedAt` set, and a test that a row committed with an older timestamp inside the overlap is still returned. Neither exists. What does exist: the mock partner API keeps tombstones in its list (`mockjira`), and `TestIntegration_DeletesAreTombstonesAndAMissingPollRowDeletesNothing` proves a poll with no row deletes nothing.

**Spoken answer (60-90 seconds).**
"The mirror cannot see deletes because my feed has nothing to show: a deleted row is simply absent, and absence in an incremental poll proves nothing. My GraphQL schema has no deletedAt and no version, so I would say plainly that it cannot sync deletes today. The three missing rows are the other classic: a row committed late with an updated_at older than the partner's watermark is never returned. My cursor gives at-least-once delivery with an inclusive updatedSince, which handles rows sharing the boundary timestamp, but it does not handle genuinely late commits. For the contract I would add a soft delete flag that moves the row forward in the feed so a delete is just another update, a monotonic version so the partner can order changes without trusting clocks, a recommended overlap window, tombstone retention, and a periodic full id reconcile as the correctness net. The mock partner API in my repo already does tombstones, so I know the shape works, but I have not added it to the GraphQL schema. For the customer today I would send a full id list to repair the 143 rows."

**Follow-ups the interviewer will ask.**
- Why not rely on webhooks for deletes? They are lossy and reorderable, so they are the fast path and the poll is the net.
- How long should tombstones live? Longer than the longest consumer outage plus one reconcile cycle; I have no measured number.
- REST or GraphQL for this partner? For bulk sync with strict idempotency I prefer REST: flat, easy to rate-limit per route and easy to reason about cost; GraphQL suits nested reads.

**Tie to your code.** [L] Keyset list with tombstones in the mock partner API: [mockjira.go](../../../../../GolangExercise/offline-sync-app/internal/mockjira/mockjira.go). The GraphQL schema that lacks tombstones: [schema.graphqls](../../../../../GolangExercise/offline-sync-app/internal/graph/schema.graphqls). Overlap on the consumer side: [extractor.go](../../../../../GolangExercise/offline-sync-app/internal/twoway/extractor.go). GraphQL tombstones and versions are design only: [K].

---

## Scenario 6 — The feed was fast, then slow after the table grew 🔴

**Situation.** Thursday 14:00. After a release that included a migration, the p95 of the second-page feed query rose from 40 ms to 1.9 s (example) as the table reached about 5 million rows (example). The release pipeline showed the migration step as "failed, retried".

**Level.** 🔴 Senior.

**What's being tested.** Reading a query plan, knowing what a failed `CREATE INDEX CONCURRENTLY` leaves behind, and not trusting EXPLAIN on a tiny table.

**Clarifying questions to ask first.**
1. Did the plan change, and did the index exist and stay valid after the migration?
2. How many rows are in the table, and when were statistics last refreshed (`ANALYZE`)?
3. Which query is slow: the first page, a later page, or the `updatedSince` form?
4. Is there a replica or lock contention involved, or only a plan problem?
5. What is the write rate? Index builds and extra indexes cost writes.

**Flow of control and data.**

```
GraphQL locations(first, after) --> SQL: WHERE (updated_at, id) > ($ts,$id) ORDER BY updated_at, id LIMIT first+1
   index (updated_at, id): seek once, read first+1 rows, no Sort     (recorded: 4 shared buffers, 0.037 ms)
   no usable index: Parallel Seq Scan + top-N heapsort                (recorded: 2,485 buffers, 19.2 ms on 100k rows)
migration CREATE INDEX CONCURRENTLY failed midway --> leaves an INVALID index the planner will not use
```

**Diagnosis steps.**
1. `EXPLAIN (ANALYZE, BUFFERS)` on the exact second-page query. Look for a Seq Scan, a Sort node, `Rows Removed by Filter`, and a large `Buffers: shared hit` count. Healthy: an Index Scan with both predicates in `Index Cond`.
2. List invalid indexes: `SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE NOT indisvalid`. A row for `disaster_locations_updated_at_id_idx` explains a failed concurrent build.
3. Migration logs: did the `CONCURRENTLY` statement run inside a transaction or fail midway?
4. Check statistics freshness (`ANALYZE`) and table size against the planner's row estimates.
5. Reproduce on production-sized data, not the dev table: on a tiny table the planner correctly prefers a Seq Scan.

**Fix now vs fix properly.**
- Now: drop the invalid index and recreate it with `CREATE INDEX CONCURRENTLY` (alone in its migration file, outside a transaction), then `ANALYZE`.
- Properly: a migration runbook for concurrent builds, a check in the pipeline for invalid indexes, a plan-shape test on production-like data, and an accounting of the write cost of each extra index. I did not measure write amplification for this index.

**How you'd test it.** The EXPLAIN comparison for this index is recorded in `docs/graphql.md` (4 buffers versus 2,485 on 100,000 synthetic rows, one local run), not a repeated benchmark. The practice analytics project has a plan-shape test, `TestIndexesChangeThePlans`, which drops the study indexes and asserts a Seq Scan with no index node, then recreates them and asserts an index plan with no Seq Scan. I would copy that idea for the feed query. I did not write that test for the feed.

**Spoken answer (60-90 seconds).**
"I would not guess, I would read the plan. The feed query orders by updated_at and id and filters with a row comparison, and my index has the same two columns in the same order, so one seek serves both the filter and the sort. In my recorded local run on 100,000 synthetic rows, that plan read 4 buffers; with the index dropped it did a parallel sequential scan and a top-N sort over 2,485 buffers. That is one local run, not production evidence. After a migration that says failed and retried, the first suspect is a failed CREATE INDEX CONCURRENTLY, which leaves an invalid index that the planner ignores. I would query the catalog for invalid indexes, then drop and recreate it, keeping that statement alone in its migration because it cannot run inside a transaction. I would also check statistics are fresh. And I would remind myself that EXPLAIN on a tiny dev table picks a sequential scan correctly, so it proves nothing about index use. What I have not measured is the write cost of this index on updates to updated_at."

**Follow-ups the interviewer will ask.**
- Why `CONCURRENTLY`? It does not block writes during the build, at the cost of being slower and non-transactional.
- Do the batched `= ANY($1)` queries have indexes? By reading the init migration the two filter columns are indexed, but I did not run EXPLAIN on them, so I would say likely and unverified.
- Would you add `totalCount`? Not for a feed; the extra `COUNT(*)` per page is the expensive part.

**Tie to your code.** [L] Index migration: [000004_locations_updated_at_id_idx.up.sql](../../../../../GolangExercise/offline-sync-app/migrations/000004_locations_updated_at_id_idx.up.sql). Keyset SQL: [pgstore.go](../../../../../GolangExercise/offline-sync-app/internal/graph/pgstore.go). Recorded EXPLAIN numbers: [graphql.md](../../../../../GolangExercise/offline-sync-app/docs/graphql.md). Plan-shape test pattern (different project): [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go). A plan-shape test for the feed query, and an invalid-index pipeline check: [K], not built.
