# Module 06 in plain English: GraphQL and API design

> **Read this first**
> - **What it is for:** learning how I built and protected a read-only GraphQL API, and how I would design an API a partner can sync from.
> - **Who it is for:** a beginner. No repo knowledge needed.
> - **Full module:** [06-graphql-and-api-design.md](../06-graphql-and-api-design.md). Read it after this file.

**Honesty lanes.** [P] = shipped at Couchbase. [L] = my own build. [K] = knowledge only.

- Everything here is **[L]**. I built and ran it myself on a local, synthetic setup.
- The code is in the sibling repo [GolangExercise/offline-sync-app](../../../../../GolangExercise/offline-sync-app/). The GraphQL service is in `internal/graph/`. The entrypoint is `cmd/graphql/main.go`. The partner-sync side is in `internal/mockjira` and `internal/twoway`.
- The library is gqlgen v0.17.95 (it generates Go code from a schema file). Go 1.26 per `go.mod`.
- The DataLoader is hand-written, about 100 lines.
- Numbers come from tests, or from measured runs recorded in `docs/graphql.md`.
- This maps to the job-description line "API patterns (REST, GraphQL, webhooks)".

---

## Phase 1: REST vs GraphQL and designing the schema

**Analogy: a restaurant menu vs a set meal.** REST is a set meal. The kitchen decides what is on the plate. GraphQL is ordering a la carte. You name each dish. But now the kitchen must stop someone ordering the whole menu.

### What GraphQL is

- GraphQL is a query language and runtime.
- The client sends one query to one endpoint and names exactly the fields it wants.
- In REST the server decides the shape of each resource. The client calls several URLs.
- So REST clients often over-fetch (get more than needed) or make extra round trips.
- My service has one route: `POST /graphql`.
- A typed schema acts as the contract.
- The trade-off: the server must defend itself against expensive queries. A fixed REST route does not need to.

### Why my GraphQL API is read-only

- All my writes already go through one audited path: `POST /api/sync`.
- It does last-write-wins upserts and writes a transactional outbox in the same transaction.
- A GraphQL mutation would be a second write path.
- That path would either repeat the guarantee or silently skip it.
- So GraphQL is the read side. The existing events and webhooks cover the push side.

### How I designed the schema

- I modelled the real tree: `Location` to `SiteAssessment` to `Photo`. I also added a `LocationStats` object.
- The top-level list is a connection. It has `edges`, a `cursor` per edge and a `pageInfo`.
- A connection gives pagination data a home that will not break clients later.
- `hasNextPage` plus `endCursor` is all a forward-only feed needs.
- Every child field that can fail is nullable: `siteAssessments`, `photos`, `stats`.
- So one failure does not null its parent.
- `location(id)` is nullable. An unknown id gives `null`, not an error.
- I left out `totalCount` on purpose. A `COUNT(*)` on every page is the expensive part, and a feed does not need it.
- Two arguments make it sync-capable: `first: Int = 20` and `updatedSince: Time`.
- `SiteAssessment.location` is a back-reference. It makes the schema cyclic. That matters in Phase 4.
- One client query returns three levels of the tree.
- In REST that would be `GET /api/locations/{id}` plus one `GET /api/sites/{id}` per assessment (noted in `docs/graphql.md`).

### REST, GraphQL or both for a partner?

- I decide by what the consumer does, not by fashion.
- For bulk sync, backfill, webhooks and writes with strict idempotency, I prefer REST.
- REST is flat, easy to rate-limit per route, easy to cache and easy to reason about for cost.
- For UI and integration clients that need different slices of a nested tree, GraphQL saves round trips.
- It also gives a typed contract you can introspect (ask the server to describe itself).
- GraphQL costs: I own query-cost defence.
- HTTP caching is mostly gone, because I serve POST only.
- Errors come back as HTTP 200 with an `errors[]` array, so generic monitoring misses them.
- What I measured: the shape of the N+1 problem. 1 + 50 + 150 = 201 store calls naive, versus 3 batched.
- I did not benchmark REST against GraphQL. I do not claim GraphQL is faster.
- In my repo they coexist: REST for writes and sync, GraphQL for reads, events for push.

### Follow-up: why POST only, and no mutations or subscriptions?

- POST only avoids cacheable and CSRF-able queries (CSRF: a website tricking a logged-in browser into sending a request). It also avoids a second code path.
- Server-to-server callers do not need CORS (the browser rule about cross-site calls).
- I skipped mutations because of the single audited write path.
- I skipped subscriptions because the WebSocket notifier already serves them.
- This is a decision for this product. A system with no outbox or audit need could reasonably expose mutations.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| GraphQL | A query language where the client names the exact fields it wants. |
| Schema | The typed contract that lists what can be asked. |
| Connection / edges / pageInfo | A standard wrapper for paged lists. |
| Nullable | A field that is allowed to be null. |
| Introspection | Asking the server to describe its own schema. |
| Over-fetching | Getting more data than you needed. |
| Mutation / subscription | GraphQL's write calls and live-update streams. |

**Say it in one breath:** I use GraphQL for nested reads, and keep writes on one audited path.

---

## Phase 2: Resolvers, the N+1 problem and DataLoader

**Analogy: a waiter taking drink orders.** A bad waiter walks to the bar once per guest. A good waiter collects all the orders at the table, then makes one trip.

### The N+1 problem

- A resolver is the function that fetches one field.
- A list resolver fetches N parents with one query.
- Then each parent's child resolver runs its own query. You pay 1 plus N queries.
- GraphQL makes this easy to hit, because each field resolves on its own and does not know its siblings.
- My nested query: 50 locations, 3 assessments each, 2 photos each.
- Naive version: 201 store calls. That is 1 plus 50 plus 150.

### What a DataLoader does

- A DataLoader collects the keys many resolvers ask for in a short window.
- Then it fetches them all with one batched query and gives each caller its own result.
- In mine, the 50 `siteAssessments` resolvers each call `Load(locationID)`.
- One query with `WHERE location_id = ANY($1)` serves all of them.
- The same query then costs 3 store calls, not 201.

### How my hand-written loader works

- `Load` takes a mutex (a lock so only one goroutine changes state at a time).
- If the key was already requested in this request, it returns the existing batch. Otherwise it enqueues the key.
- The first key of a batch starts a timer. The default is 2 ms.
- The batch is sent when the timer fires, or when it reaches `MaxBatch`, which is 500.
- A `sent` flag checked under the mutex stops the size flush and the timer from both running the same batch.
- Waiters block on the batch's `done` channel, or on their own context.
- The batch function returns a map from key to value. A missing key gives the zero value and no error.
- gqlgen resolves list elements concurrently. That is why 50 resolvers arrive inside the same window.
- The resolver itself stays four lines. All the batching intelligence is in the loader.
- The resolver has no idea how many siblings exist.
- The naive resolver differs by one thing: a one-element slice instead of the loader. That alone gives 50 queries instead of one.

### Failure modes of owning a DataLoader

- It adds up to the wait window (2 ms) of latency per nesting level.
- Batch boundaries are not deterministic under load. A split batch costs one extra query but never gives wrong data.
- The cache has no invalidation and no user scoping. So it must be per request.
- I build a new `Loaders` set in `requestScope`. A test shows two identical requests hit the store twice.
- A fetch error is stored on the batch and returned to every waiter. It stays cached for the rest of that request.
- The batch runs on a timer goroutine that gqlgen's panic recovery does not cover.
- So `run` recovers panics itself and turns them into an error.
- Numbers I stand behind: 201 versus 3 store calls on a fake store, and 3 SQL statements on real Postgres. Tests assert both.
- I did not measure the latency cost of the 2 ms window.
- I did not benchmark my loader against `dataloadgen` or gqlgen's built-in batch resolvers.

### Follow-up: why not a library, and how do I test a timer without flakes?

- `docs/graphql.md` records that gqlgen's docs recommend `vikstrous/dataloadgen`.
- I would use it in production if I did not want to own the code.
- I wrote it by hand so I can defend every line.
- My first tests flaked when 24 race-enabled processes ran on 2 CPUs. The 2 ms window split batches.
- Now the tests set `MaxBatch` to the expected key count and flush by size. A 5-second timer is only a safety net.
- Consequence: the tests prove batching logic and call counts. They do not exercise the real 2 ms timer under production load.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Resolver | The function that fetches one field. |
| N+1 problem | One query for the list, then one more per item. |
| DataLoader | Collects keys in a short window and fetches them in one query. |
| Batch | A group of keys fetched together. |
| Mutex | A lock that lets one goroutine touch shared state at a time. |
| Per-request cache | A cache thrown away at the end of each request. |

**Say it in one breath:** A DataLoader turns 1+N+M queries into one query per nesting level, and I proved it as 201 calls down to 3.

---

## Phase 3: Pagination with keyset cursors

**Analogy: a bookmark vs counting pages.** Offset is "go to page 400 by counting from page 1 each time". Keyset is a bookmark that you open straight to.

### Offset vs keyset

- Offset pagination makes the database skip N rows on every page. It gets slower as the offset grows.
- It is also unstable under writes. If a row is inserted before your offset, you skip or repeat rows.
- Keyset pagination remembers the last row's position and seeks straight to it.
- Cost stays flat and the walk is stable.
- A cursor is an opaque token (the client must not look inside) that says where the previous page ended.
- Mine is a base64url string. The client sends back `endCursor` as `after`.
- Inside: the last row's `updated_at` and `id`.

### How my cursor and SQL work

- The cursor is base64url of the last row's `updated_at` in Unix microseconds, a pipe, and the UUID.
- Microseconds match what `timestamptz` stores, so a round trip is lossless.
- The query orders by `(updated_at, id)`.
- It filters with a row comparison: `(updated_at, id) > ($ts, $id)`.
- Many rows can share one timestamp. They are still ordered and none is lost.
- I ask the store for `first + 1` rows. The extra row only decides `hasNextPage`.
- A garbage cursor gets `BAD_USER_INPUT` before the store is touched.
- Only placeholders go into the SQL text. Every value is a bind argument.
- The `ORDER BY` and the comparison use the same `(updated_at, id)` order on purpose. Phase 6 shows one index then serves both.

### What guarantees pagination gives, and where it breaks

- It gives at-least-once delivery. It never skips.
- `id` is the tiebreaker because many rows can share one `updated_at`.
- My integration test seeds groups of 5 rows with one timestamp and pages by 7.
- `docs/graphql.md` records a manual mutation run that dropped `id` from the comparison. It lost 15 of 50 rows.
- A row updated mid-walk gets a bigger `updated_at`. It moves to the end and is delivered again, not skipped.
- The consumer handles this by deduplicating on `id`.
- `updatedSince` is inclusive (`>=`). A poller that restarts from the max timestamp it saw re-reads boundary rows instead of missing them.
- That is safe only because applying a row twice is idempotent (the same result as once).
- Limits: the connection is forward-only. There is no `hasPreviousPage` or `totalCount`.
- The cursor is only base64, not signed. From reading the code, a client can forge one.
- A forged cursor only selects a position. An invalid one returns `BAD_USER_INPUT`.
- A late commit with an older `updated_at` than the consumer's checkpoint is still missed. This is not exactly-once.

### Follow-up: why `updated_at|id` and not a row number? Could the sort key differ?

- A row number would be offset pagination in disguise. It drifts under writes.
- The pair `(updated_at, id)` identifies a position in the sort order itself.
- A sort key should be immutable or monotonic for a stable walk. `updated_at` is neither.
- That is why a touched row reappears.
- I accept it. For a sync feed, re-delivery is the safe direction.
- For a UI list sorted by `created_at`, I would prefer an immutable key.
- I only built and tested the `updated_at` ordering.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Offset pagination | Skip N rows, then take a page. Slow and unstable. |
| Keyset pagination | Continue after the last row's sort key. Fast and stable. |
| Cursor | An opaque bookmark for the next page. |
| Tiebreaker | A second sort column (here `id`) for rows with equal timestamps. |
| Bind argument | A value sent separately from the SQL text, so it cannot inject SQL. |
| At-least-once | Every row arrives, but some may arrive twice. |

**Say it in one breath:** I page by position, not by count, using `(updated_at, id)`, so reads are stable and a consumer can safely dedupe repeats.

---

## Phase 4: Safety: depth and cost limits, and authentication

**Analogy: a bouncer who checks the order before the kitchen starts.** If the order is for the entire menu twelve times, the bouncer says no. The kitchen never wastes a minute.

### Why GraphQL is easier to abuse

- In REST each route has a roughly known cost.
- In GraphQL the client writes the query. It can ask for a deep or very wide tree in one request.
- My schema is cyclic: `Location` has `siteAssessments`, and `SiteAssessment` has `location`.
- A client could nest forever.
- A DAG schema (a graph with no cycles) cannot be deep. The back-reference creates the attack.
- So I check depth, size and estimated cost before running anything.

### Authentication

- The handler takes an auth middleware as a parameter and applies it outermost.
- In production that is the Cognito ID-token verifier, the same one the REST API uses.
- A missing, garbage, wrong-scheme or expired token gets 401. The store receives zero calls.
- An unauthenticated request never allocates loaders or touches the store.
- Every authenticated user can read every location today. There is no row-level authorization yet.

### My layered limits and the cost formula

- The checks run cheapest first.
- Parser token limit: 5,000.
- Depth: at most 8.
- Expanded field count: at most 1,000.
- Estimated complexity: at most 10,000.
- Page-size cap: 100.
- Request timeout: 10 seconds.
- Complexity is estimated rows materialised. Scalars cost 0. Each object costs 1.
- `locations` multiplies by `first`.
- `siteAssessments` assumes 10 per location. `photos` assumes 10 per assessment.
- I clamp `first` before multiplying. The resolver rejects bad values only after the complexity check, and a huge value could overflow into a cheap negative number.
- Violations return HTTP 422, via `errcode.RegisterErrorType`. gqlgen's default would answer 200.
- My `measure` function remembers (memoises) each fragment by name.
- So a fragment bomb (fragments that reference fragments to blow up the query) is walked in linear time.
- gqlgen's own complexity walk re-expands every spread. That is why I wrote `measure`.

### What the defence stops and what it does not

- It stops deep cyclic queries, fragment bombs, aliased fan-out and oversized documents.
- It rejects them before any resolver or store call runs. Tests assert zero store calls on rejection.
- Documented numbers: `first: 50` with full nesting costs 5,600 and is accepted.
- `first: 100` costs 11,200 and is rejected.
- 10 aliases of a 1,200 page cost 12,000 and are rejected.
- Tests assert the accept and reject outcomes. The arithmetic follows from `complexityRoot`.
- The deepest legitimate query has depth 7 against a limit of 8. A 20-hop cycle has depth 42.
- The constants are policy, not truth.
- 10 assessments per location is an estimate, because nothing caps it.
- 10 photos per assessment is real, because `UpsertPhoto` caps it.
- Gaps I name plainly: no per-client rate limiting, no persisted-query allowlist.
- I did not test the gqlparser validator itself against fragment bombs, because it runs before my code.

### Follow-up: an authenticated hostile client that stays under every limit

- Cost limits bound one request. They do not bound a flood of valid ones.
- That needs a rate limit per client at the gateway or WAF. `docs/graphql.md` lists it as not covered.
- Ideally also persisted queries, so only known documents run.
- If row-level authorization arrives, it belongs in the `Store` as a SQL `WHERE`. Then loaders cannot bypass it.
- I have not built either. Describe them as next steps, not features.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Query depth | How many levels of nesting a query has. |
| Complexity / cost | An estimate of how much work a query causes. |
| Fragment bomb | Fragments that reference each other to blow up the query size. |
| Aliased fan-out | Asking for the same expensive field many times under different names. |
| Persisted query | A query saved on the server; clients send only its id. |
| Row-level authorization | Rules about which rows each user may see. |
| WAF | A web application firewall in front of the API. |

**Say it in one breath:** I authenticate first and reject deep or expensive queries before any resolver runs; per-client rate limiting is still missing.

---

## Phase 5: Errors and partial results

**Analogy: a restaurant where one dish is out of stock.** The waiter serves the rest of the meal and says "no dessert today". They do not cancel the whole table.

### What a GraphQL error looks like

- A response has `data` and an optional `errors` array.
- Each error can carry a `path` to the field that failed.
- The HTTP layer succeeded, because the server parsed and ran the query. A field failure is not a transport error.
- In my service, parse, validation and limit errors return 422.
- A failing child field returns 200 with the rest of the data.
- Consequence: monitoring based on status codes alone misses resolver failures.

### If the photos query fails

- The response is 200.
- All locations and assessments are present.
- `photos` is `null`, with one `errors[]` entry per affected path.
- That works only because `photos` is nullable.
- A non-null field would null its nearest nullable parent, up to `data: null`.
- My error presenter masks resolver errors.
- An error with a path and no code is replaced with `internal error` and logged on the server.
- So SQL text and host names never reach a client.
- Errors with no path (protocol errors) pass through unchanged.
- Errors with a code such as `BAD_USER_INPUT` also pass through.
- The test seeds a fake password into the store error and asserts it never appears in the response.
- That proves the masking is real, not just intended.

### Sharp edges of partial results

- Nullability is the reliability contract.
- A nullable child promises that its failure degrades one path.
- A non-null field promises that its failure may erase its parent.
- One failed batch is one query but N errors, one per waiting field.
- My test shows 6 errors from one photos batch call. The response is still 200.
- `Query.locations` is non-null on purpose. If the root list fails, there is nothing to return.
- The test shows `data: null` with exactly one masked error.
- A resolver must return an error, not panic. gqlgen nulls the entire list when an element panics.
- The masking rule is a heuristic keyed on path and code.
- Any resolver error that someone tags with a code would pass through to the client.
- Today only `BAD_USER_INPUT` is used that way.
- I asserted these behaviours with a fake store.
- I have not measured error rates. I have not built any metric on the presenter.

### Follow-up: how do I monitor an API where every error is 200?

- The presenter already logs the real error with its path.
- First step: emit a counter from `presentError`, labelled by path and code, and alert on its rate.
- Also alert on status codes for the 422 limit violations, which I made visible to gateways on purpose.
- That is a design, not built. Today the presenter only logs. There are no metrics or tracing in this service.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Partial result | A response with some data and some errors. |
| `errors[]` | The list of failures in a GraphQL response. |
| Path | Where in the response tree a failure happened. |
| Error masking | Hiding internal details behind a safe message. |
| Non-null (`!`) | A field that must never be null; failure bubbles up. |
| Error presenter | Code that shapes each error before the client sees it. |

**Say it in one breath:** A failing child field degrades one path, and I mask internal errors so clients never see SQL.

---

## Phase 6: Performance and the supporting index (EXPLAIN)

**Analogy: a book's index vs reading every page.** To find "pagination" you can flip to the index and jump to the page. Or you can read the whole book each time.

### Why keyset pagination needs an index

- An index is a sorted structure (a B-tree in Postgres).
- It finds rows by key without reading the whole table.
- Keyset pagination asks for rows after a position, in a given order.
- Without an index, the database scans and sorts the table for every page.
- With an index in the same order as the query, it seeks to the position and reads only the page.

### The index I added and how I proved it works

- I added a B-tree on `disaster_locations (updated_at, id)`.
- Same column order as the `ORDER BY` and the row comparison. One seek serves both the filter and the order.
- I created it `CONCURRENTLY`, so building it does not block writes.
- That means it cannot run in a transaction. It must be the only statement in the migration.
- To prove it, I ran `EXPLAIN (ANALYZE, BUFFERS)` on the second-page query.
- The data was 100,000 seeded rows, inside a rolled-back transaction.
- I ran it once with the index and once with it dropped in the same transaction.
- What to look for: an `Index Scan` with both predicates in `Index Cond`, a small `Buffers: shared hit`, and no `Sort` node.
- I did not run the exact example statement in the module in this session. The recorded results are in `docs/graphql.md`.

### The numbers and what they prove

- With the index: an `Index Scan` on `disaster_locations_updated_at_id_idx`, 51 rows, 4 shared buffers, 0.037 ms.
- Without it: a parallel sequential scan plus a top-N heapsort.
- 27,024 rows removed by the filter per loop, 2,485 shared buffers, 19.2 ms.
- That is roughly 600 times fewer buffers.
- But it is one local run, on synthetic data, in one Postgres instance. It is not a repeated benchmark and not production data.
- On the 50 rows that the integration tests leave behind, the planner picks `Seq Scan` plus `Sort`. That is correct for a one-page table.
- So an EXPLAIN on a tiny dev table proves nothing about index use.
- Failure mode of `CREATE INDEX CONCURRENTLY`: a failure midway leaves an `INVALID` index. Drop it before retrying.
- Write cost: every update of `updated_at` now touches this index.
- I reason it is acceptable for a read-heavy feed. I did not measure write amplification.

### Follow-up: do the batched `= ANY($1)` queries have indexes too?

- From reading `migrations/000001_init_schema.up.sql`, `site_assessments(location_id)` and `photos(site_assessment_id)` both have indexes.
- Those are the columns the two batch queries filter on.
- I did not run EXPLAIN on those queries. Say "likely served by the indexes, not verified".
- `MaxBatch` of 500 bounds the size of each `ANY` list.
- I have not measured how the planner behaves at that size.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Index (B-tree) | A sorted lookup structure that avoids scanning the whole table. |
| EXPLAIN (ANALYZE, BUFFERS) | Postgres shows the real plan, timing and pages read. |
| Index Scan / Seq Scan | Seek through the index / read the whole table. |
| Buffers | Pages of memory or disk the query touched. |
| CONCURRENTLY | Build an index without blocking writes. |
| INVALID index | A half-built index left after a failed concurrent build. |
| Write amplification | Extra write work caused by maintaining indexes. |

**Say it in one breath:** I added an index in the query's order, and one local EXPLAIN showed 4 buffers instead of 2,485.

---

## Phase 7: Designing an API a partner can safely sync from

**Analogy: a newspaper delivery with a stub for each issue.** You say "I last got issue 40". They hand you 41 onward, numbered. If you ring twice, they resend the same issue, not a new one.

### What a partner needs

- The partner needs to fetch only what changed since its last run.
- It needs stable pages, with no loss or duplicates.
- That means an `updated_since` filter, a cursor for paging within one run, and a stable id to dedupe.
- It needs to learn about deletes.
- It needs a safe way to retry a write.
- The server should tell it to slow down when it calls too fast.

### What an idempotency key is

- A client-chosen token sent with a write.
- If the request is retried, the server returns the first result instead of applying the change twice.
- In my two-way sync, the push to the partner carries the domain event id as the `Idempotency-Key`.
- If the first call worked but its response was lost, the retry replays the original answer.

### The pull side: cursor plus `updated_since`

- My mock partner API lists issues keyset-paginated on `(UpdatedAt, ID)`.
- It takes `updated_since` as RFC 3339 (a standard date-time format) and a `cursor`.
- It returns `nextCursor`, which is empty on the last page.
- The filter is inclusive. The cursor continues strictly after the last position.
- On my side, the extractor starts an incremental run at the stored watermark minus an overlap window.
- So late commits and timestamp granularity cannot cause skips.
- Then it applies each page and its checkpoint in one transaction.
- The re-reads from the overlap are free. Applying an already-seen version is a no-op through the version gate.
- The watermark only advances after the last page.
- `apply` must be idempotent, because the overlap re-delivers on purpose.
- The real extractor also commits a checkpoint per page, so a crash resumes from the cursor.

### The full contract and where my code stops

- The contract: a monotonic version plus `updatedAt` per record.
- A keyset cursor on `(updatedAt, id)`.
- An inclusive `updated_since`.
- A bounded page size.
- Tombstones for deletes.
- Idempotency keys on writes.
- 429 with `Retry-After` for rate limits.
- Webhooks for the push half, and a poll as the repair path.
- In the mock partner API, delete sets a `Deleted` flag, bumps the version and keeps the row.
- The list includes tombstones, so an incremental pull can see deletes.
- A missing row in a poll is never treated as a delete. A test asserts an empty poll deletes nothing.
- On the consumer side, `delay()` honours `Retry-After` when present. Otherwise it uses full-jitter exponential backoff.
- Gap: my GraphQL schema has no tombstones and no version field.
- So deletes cannot be synced through GraphQL.
- A partner cannot order conflicting changes by version there, only by `updatedAt`.
- The mock's idempotency map is unbounded, has no expiry, and does not check that a repeated key carries the same body.
- The mock's `limit` of zero returns everything. A real API must cap the page size.
- The mock has no real rate limiter. It only has on-demand 429 fault injection.
- The GraphQL service has no per-client limiter either.
- Late commits older than the overlap are missed unless there is a periodic full reconcile. I did not build it.

### Follow-up: how to add tombstones to the GraphQL feed

- Soft-delete rows with a nullable `deletedAt`.
- Keep them in the `(updated_at, id)` feed. A delete is just another update that moves the row forward.
- Expose that field so the consumer can apply it as a delete.
- Also expose a monotonic `version`, so the partner can order changes without trusting clocks.
- Add a retention policy for old tombstones.
- This is a design only. None of it exists in the schema today.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| `updated_since` | A filter that returns only rows changed after a time. |
| Watermark | The time up to which everything has been synced. |
| Overlap window | Start slightly before the watermark to avoid missing late rows. |
| Tombstone | A "deleted" flag on a kept row. |
| Idempotency key | A token that makes a retried write safe. |
| Retry-After | A header telling the client how long to wait before retrying. |
| Reconcile | Compare both sides in full and repair differences. |

**Say it in one breath:** A sync-safe API needs versions, a cursor, `updated_since`, tombstones, idempotency keys and rate-limit hints; my GraphQL feed has only the cursor and `updated_since`.

---

## Mix-ups to avoid

- Do not say GraphQL is faster than REST. I measured query counts and one plan, not latency.
- Do not say GraphQL errors are HTTP errors. A failing child field is 200 with `errors[]`. Only parse, validation and limit errors are 422 in my service.
- Do not mix up the N+1 count (201 versus 3 store calls) with a latency claim.
- Do not call the cursor secure. It is base64 only, not signed. It only selects a position.
- Do not say the GraphQL schema can sync deletes. It has no tombstones and no version field. The mock partner REST side has tombstones.
- Do not say `mockjira` is Jira. Its payloads, headers and pagination are invented for tests.

## What I built vs what I only know

**Built [L], local and synthetic only:**

- A read-only gqlgen GraphQL service with a hand-written DataLoader.
- Keyset cursors on `(updated_at, id)`, and a `CONCURRENTLY` index.
- Layered depth, field, complexity and page limits, with auth outermost and error masking.
- A mock partner API with cursor, `updated_since`, tombstones and idempotency-key replay.
- A consumer extractor with overlap and per-page checkpoints.

**Shipped [P]:** nothing in this module.

**Knowledge only [K]:** `dataloadgen` as the library gqlgen recommends (from `docs/graphql.md`), and the design of tombstones in GraphQL, per-client rate limiting and persisted queries.

**Not built:** rate limiting, persisted queries, row-level authorization, GraphQL tombstones or version fields, error-rate metrics, a full reconcile.

**Not claimed:**

- GraphQL faster than REST.
- The cost of the 2 ms window, loader versus `dataloadgen`, or index write amplification.
- The EXPLAIN result as production evidence. It is one local run on 100,000 synthetic rows.
- Full fragment-bomb validation. I did not test the gqlparser validator itself.
- That the mutation-run figures (15 of 50 rows lost, 201 versus 3 with `MaxBatch` 1) were re-run for the module. They are recorded in `docs/graphql.md`.
- Exactly-once. The design is at-least-once with idempotent apply.
