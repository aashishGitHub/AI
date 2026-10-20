# Module 06 — GraphQL & API design

> This module covers how I designed, protected and operated a read-only GraphQL API, and how I would design an API that a partner can safely sync from; it maps to the JD line "API patterns (REST, GraphQL, webhooks)". All the code is my own build in `GolangExercise/offline-sync-app`: the GraphQL service lives in `internal/graph/` with its entrypoint in `cmd/graphql/main.go`, and the partner-sync side lives in `internal/mockjira` and `internal/twoway`. The library is gqlgen v0.17.95 (schema-first code generation, Go 1.26 per `go.mod`) with a hand-written DataLoader of about 100 lines. Every item is lane [L], meaning I built and ran it myself; numbers come from tests or from the measured runs recorded in `docs/graphql.md`, all on a local synthetic setup.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. REST vs GraphQL and designing the schema | Choose the style per consumer and model the data as a typed, paginated graph. | `internal/graph/schema.graphqls`, `docs/graphql.md` |
| 2. Resolvers, the N+1 problem and DataLoader | Turn 1+N+M queries into one query per nesting level. | `dataloader.go`, `loaders.go`, `schema.resolvers.go`, `nplusone_test.go` |
| 3. Pagination with keyset cursors | Page by position, not by offset, so reads are stable and double as a sync checkpoint. | `cursor.go`, `pgstore.go`, `integration_test.go` |
| 4. Safety: depth and cost limits, and authentication | Make a hostile or careless query cheap to reject and keep unauthenticated traffic away from the store. | `limits.go`, `handler.go`, `authn_test.go`, `safety_test.go` |
| 5. Errors and partial results | Let a failing child field degrade one path instead of the whole response, without leaking internals. | `handler.go` (`presentError`), `resolver.go`, `safety_test.go` |
| 6. Performance and the supporting index (EXPLAIN) | Prove with a plan, not a guess, that the page query seeks instead of scanning. | `migrations/000004_...up.sql`, `docs/graphql.md` |
| 7. Designing an API a partner can safely sync from | Cursor plus `updated_since`, tombstones, idempotency keys and rate limits as one contract. | `internal/mockjira`, `internal/twoway`, `docs/two-way-sync.md` |

## Phase 1 — REST vs GraphQL and designing the schema

### 🟢 Beginner

**Q:** What is GraphQL, and how is it different from REST?

**A:** GraphQL is a query language and runtime where the client sends one query to one endpoint and names exactly the fields it wants. In REST the server decides the shape of each resource and the client calls several URLs, so it often over-fetches or makes extra round trips. In my service there is a single route, `POST /graphql`, and a typed schema that acts as the contract. The trade-off is that the server must now defend itself against expensive queries, which a fixed REST route does not need to do.

**Q:** Why did you make the GraphQL API read-only?

**A:** In my system all writes already go through one audited path, `POST /api/sync`, which does last-write-wins upserts and writes a transactional outbox in the same transaction. A GraphQL mutation would have been a second write path that either has to repeat that guarantee or silently bypass it. So GraphQL is the read side, and the existing events and webhooks cover the push side.

### 🟡 Intermediate

**Q:** How did you design the schema, and why connection types instead of a plain list?

**A:** I modelled the real tree, `Location` to `SiteAssessment` to `Photo`, plus a `LocationStats` object, and exposed the top-level list as a connection with `edges`, a `cursor` per edge and a `pageInfo`. I chose a connection because pagination metadata needs a home that does not break clients later, and `hasNextPage` plus `endCursor` is all a forward-only feed needs. I made every fallible child field nullable, such as `siteAssessments`, `photos` and `stats`, so one failure does not null its parent, and `location(id)` is nullable so an unknown id is `null` rather than an error. I deliberately left out `totalCount` because a `COUNT(*)` on every page is the expensive part of a feed that never needs it.

**Source:** `GolangExercise/offline-sync-app/internal/graph/schema.graphqls:9-27`
```graphql
type Query {
  locations(first: Int = 20, after: String, updatedSince: Time): LocationConnection!
  location(id: ID!): Location
}

type LocationConnection {
  edges: [LocationEdge!]!
  pageInfo: PageInfo!
}

type LocationEdge {
  cursor: String!
  node: Location!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/schema.graphqls:29-48`
```graphql
type Location {
  id: ID!
  name: String!
  latitude: Float!
  longitude: Float!
  createdAt: Time!
  updatedAt: Time!
  siteAssessments: [SiteAssessment!]
  stats: LocationStats
}

type SiteAssessment {
  id: ID!
  name: String!
  notes: String!
  createdAt: Time!
  updatedAt: Time!
  location: Location
  photos: [Photo!]
}
```

I would point at `first: Int = 20` and `updatedSince: Time` as the two arguments that make this a sync-capable feed, and at `SiteAssessment.location` as the back-reference that makes the schema cyclic, which becomes important in phase 4.

**Illustrative (not from the repo):**
```graphql
query ($first: Int, $after: String, $since: Time) {
  locations(first: $first, after: $after, updatedSince: $since) {
    edges { cursor node { id name siteAssessments { id photos { id } } } }
    pageInfo { hasNextPage endCursor }
  }
}
```

That is the client side of the same schema: one request returns three levels of the tree, which in REST would be `GET /api/locations/{id}` followed by one `GET /api/sites/{id}` per assessment, as noted in `docs/graphql.md`.

### 🔴 Senior

**Q:** A partner wants to integrate with our product. Do you give them REST, GraphQL or both, and how do you decide?

**A:** I decide by what the consumer does, not by fashion. For bulk sync, backfill, webhooks and writes with strict idempotency, I prefer REST because it is flat, easy to rate-limit per route, easy to cache and easy to reason about cost. For UI and integration clients that need different slices of a nested tree, GraphQL saves round trips and gives a typed, introspectable contract. The cost of GraphQL is that I own query-cost defence, HTTP caching is mostly gone because I serve POST only, and errors come back as HTTP 200 with an `errors[]` array, so generic monitoring misses them. What I measured is the shape of the N+1 problem (1 + 50 + 150 = 201 store calls naive versus 3 batched), not a REST-versus-GraphQL latency comparison, and I have not benchmarked the two against each other, so I would not claim GraphQL is faster. In my repo they coexist: REST for writes and sync, GraphQL for reads, events for push.

**Follow-up they will ask:** Why POST only, and why no mutations or subscriptions?

**A:** POST only avoids cacheable and CSRF-able queries and a second code path, and server-to-server callers do not need CORS. I skipped mutations because of the single audited write path, and I skipped subscriptions because the WebSocket notifier already serves them. The boundary of that claim is that it is a decision for this product: a system with no outbox or audit requirement could reasonably expose mutations.

## Phase 2 — Resolvers, the N+1 problem and DataLoader

### 🟢 Beginner

**Q:** What is the N+1 problem?

**A:** A list resolver fetches N parents with one query, and then each parent's child resolver issues its own query, so you pay 1 plus N queries. GraphQL makes this easy to hit because each field resolves independently and does not know about its siblings. In my nested query over 50 locations, 3 assessments each and 2 photos each, the naive version issued 201 store calls, which is 1 plus 50 plus 150.

**Q:** What does a DataLoader do about it?

**A:** A DataLoader collects the keys requested by many resolvers during a short window, then fetches them all with one batched query and hands each caller its own result. In my implementation the 50 `siteAssessments` resolvers each call `Load(locationID)`, and one query with `WHERE location_id = ANY($1)` serves all of them. The same query then costs 3 store calls instead of 201.

### 🟡 Intermediate

**Q:** Walk me through how your hand-written DataLoader works.

**A:** `Load` takes a mutex, returns the existing batch if the key was already requested in this request, and otherwise enqueues the key. The first key of a batch starts a timer, 2 ms in the default config, and the batch is sent when the timer fires or when it reaches `MaxBatch`, which is 500. A `sent` flag checked under the mutex makes sure the size flush and the timer cannot both run the same batch. Waiters block on the batch's `done` channel or on their own context, and the batch function returns a map from key to value, so a missing key yields the zero value and no error. gqlgen resolves list elements concurrently, which is why 50 resolvers arrive inside the same window.

**Source:** `GolangExercise/offline-sync-app/internal/graph/dataloader.go:43-58`
```go
func (l *DataLoader[K, V]) Load(ctx context.Context, key K) (V, error) {
	l.mu.Lock()
	b, cached := l.batches[key]
	if !cached {
		b = l.enqueue(ctx, key)
	}
	l.mu.Unlock()

	select {
	case <-b.done:
		return b.results[key], b.err
	case <-ctx.Done():
		var zero V
		return zero, ctx.Err()
	}
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/dataloader.go:60-76`
```go
func (l *DataLoader[K, V]) enqueue(ctx context.Context, key K) *batch[K, V] {
	b := l.pending
	if b == nil {
		b = &batch[K, V]{done: make(chan struct{})}
		l.pending = b
		time.AfterFunc(l.cfg.Wait, func() { l.flush(ctx, b) })
	}
	b.keys = append(b.keys, key)
	l.batches[key] = b

	if len(b.keys) >= l.cfg.MaxBatch {
		b.sent = true
		l.pending = nil
		go l.run(ctx, b)
	}
	return b
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/schema.resolvers.go:16-22`
```go
func (r *locationResolver) SiteAssessments(ctx context.Context, obj *Location) ([]*SiteAssessment, error) {
	rows, err := loadersFrom(ctx).SiteAssessments.Load(ctx, obj.ID)
	if err != nil {
		return nil, err
	}
	return mapSlice(rows, newSiteAssessment), nil
}
```

I would say that the resolver stays four lines because all the batching intelligence lives in the loader, and that the resolver contains no knowledge of how many siblings exist.

**Illustrative (not from the repo):**
```go
func (r *locationResolver) SiteAssessments(ctx context.Context, obj *Location) ([]*SiteAssessment, error) {
	rows, err := r.Store.SiteAssessmentsByLocationIDs(ctx, []uuid.UUID{obj.ID})
	if err != nil {
		return nil, err
	}
	return mapSlice(rows, newSiteAssessment), nil
}
```

This is the naive resolver I compare against, a fragment that I did not compile. The only difference is a one-element slice instead of the loader, and that single difference is what produces 50 queries instead of one.

### 🔴 Senior

**Q:** What are the failure modes of owning a DataLoader, and where does your claim stop?

**A:** The loader adds up to the wait window, 2 ms, of latency per nesting level, and batch boundaries are non-deterministic under load, so a split batch costs one extra query but never wrong data. The cache has no invalidation and no user scoping, so it must be per request; I build a new `Loaders` set in `requestScope` and have a test that two identical requests hit the store twice. A fetch error is stored on the batch and returned to every waiter and stays cached for the rest of that request. The batch runs on a timer goroutine that gqlgen's panic recovery does not cover, so `run` recovers panics itself and turns them into an error. The numbers I can stand behind are 201 versus 3 store calls on a fake store and 3 SQL statements on real Postgres, both asserted by tests; I did not measure the latency cost of the 2 ms window, and I did not benchmark my loader against `dataloadgen` or gqlgen's built-in batch resolvers.

**Source:** `GolangExercise/offline-sync-app/internal/graph/dataloader.go:91-100`
```go
// run executes on a timer goroutine that gqlgen's panic recovery does not cover, so a panic must not escape.
func (l *DataLoader[K, V]) run(ctx context.Context, b *batch[K, V]) {
	defer close(b.done)
	defer func() {
		if r := recover(); r != nil {
			b.err = fmt.Errorf("batch fetch panicked: %v", r)
		}
	}()
	b.results, b.err = l.fetch(ctx, b.keys)
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/nplusone_test.go:109-120`
```go
func TestNPlusOne_LoaderCacheIsPerRequest(t *testing.T) {
	store := newFakeStore(1, 0, 0)
	h := newTestHandler(store)
	q := `{ location(id: "` + testID(kindLocation, 0).String() + `") { id } }`

	post(t, h, q, nil)
	post(t, h, q, nil)

	if got := store.callCount("LocationsByIDs"); got != 2 {
		t.Fatalf("LocationsByIDs calls over two identical requests = %d, want 2; a cache shared across requests would give 1", got)
	}
}
```

**Follow-up they will ask:** Why not use a library, and how do you test something timer-driven without flakes?

**A:** `docs/graphql.md` records that gqlgen's own docs recommend `vikstrous/dataloadgen`, and that I would use it in production if I did not want to own the code; I wrote it by hand so I can defend every line. For testing, the first version of my tests flaked when 24 race-enabled processes ran on 2 CPUs, because the 2 ms window split batches, so the tests now set `MaxBatch` to the expected key count and flush by size, with a 5-second timer only as a safety net. The consequence is that the tests prove the batching logic and the call counts, but they do not exercise the real 2 ms timer path under production load.

## Phase 3 — Pagination with keyset cursors

### 🟢 Beginner

**Q:** Why not use offset pagination?

**A:** Offset pagination makes the database skip N rows on every page, so it gets slower as the offset grows. It is also unstable under writes: if a row is inserted before your offset while you are paging, you skip or repeat rows. Keyset pagination remembers the last row's position and seeks straight to it, so cost stays flat and the walk is stable.

**Q:** What is a cursor?

**A:** A cursor is an opaque token that tells the server where the previous page ended. In my API it is a base64url string, and the client is supposed to treat it as a black box and just send back `endCursor` as `after`. Inside, it carries the last row's `updated_at` and `id`.

### 🟡 Intermediate

**Q:** How is your cursor built, and what SQL does it produce?

**A:** The cursor is base64url of the last row's `updated_at` in Unix microseconds, a pipe, and the UUID. Microseconds are used because they match what `timestamptz` stores, so a round trip is lossless. The query orders by `(updated_at, id)` and filters with a row comparison, `(updated_at, id) > ($ts, $id)`, so many rows sharing one timestamp are still ordered and none is lost. I ask the store for `first + 1` rows and use the extra row only to compute `hasNextPage`. A garbage cursor is rejected with `BAD_USER_INPUT` before the store is touched.

**Source:** `GolangExercise/offline-sync-app/internal/graph/cursor.go:16-40`
```go
// Microsecond precision matches what timestamptz stores, so a round trip is lossless.
func EncodeCursor(c Cursor) string {
	raw := fmt.Sprintf("%d|%s", c.UpdatedAt.UnixMicro(), c.ID)
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

func DecodeCursor(s string) (Cursor, error) {
	raw, err := base64.RawURLEncoding.DecodeString(s)
	if err != nil {
		return Cursor{}, ErrInvalidCursor
	}
	micros, id, ok := strings.Cut(string(raw), "|")
	if !ok {
		return Cursor{}, ErrInvalidCursor
	}
	us, err := strconv.ParseInt(micros, 10, 64)
	if err != nil {
		return Cursor{}, ErrInvalidCursor
	}
	parsed, err := uuid.Parse(id)
	if err != nil {
		return Cursor{}, ErrInvalidCursor
	}
	return Cursor{UpdatedAt: time.UnixMicro(us).UTC(), ID: parsed}, nil
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/pgstore.go:65-88`
```go
// Only placeholders are interpolated into the SQL text; every value travels as a bind argument.
func listLocationsSQL(p ListParams) (string, []any) {
	var (
		conds []string
		args  []any
	)
	if p.UpdatedSince != nil {
		args = append(args, *p.UpdatedSince)
		conds = append(conds, fmt.Sprintf("updated_at >= $%d", len(args)))
	}
	if p.After != nil {
		args = append(args, p.After.UpdatedAt, p.After.ID)
		conds = append(conds, fmt.Sprintf("(updated_at, id) > ($%d, $%d)", len(args)-1, len(args)))
	}
	args = append(args, p.Limit)

	var q strings.Builder
	q.WriteString("SELECT " + locationCols + " FROM disaster_locations")
	if len(conds) > 0 {
		q.WriteString(" WHERE " + strings.Join(conds, " AND "))
	}
	fmt.Fprintf(&q, " ORDER BY updated_at, id LIMIT $%d", len(args))
	return q.String(), args
}
```

I would stress that only placeholders are interpolated into the SQL text and every value travels as a bind argument, and that the `(updated_at, id)` order in the `ORDER BY` and in the comparison is identical on purpose, because phase 6 shows that is what lets one index serve both.

### 🔴 Senior

**Q:** What guarantees does your pagination give a consumer, and where does it break?

**A:** It gives at-least-once delivery, never skip. `id` is the tiebreaker because many rows can share one `updated_at`; my integration test seeds groups of 5 rows with one timestamp and pages by 7, and `docs/graphql.md` records that a manual mutation run that dropped `id` from the comparison lost 15 of 50 rows. A row updated mid-walk gets a larger `updated_at`, so it moves to the end and is delivered again rather than skipped, which the consumer handles by deduplicating on `id`. `updatedSince` is inclusive (`>=`) so a poller that restarts from the max timestamp it saw re-reads boundary rows instead of missing ones, which is safe only because applying a row twice is idempotent. The limits are that the connection is forward-only with no `hasPreviousPage` or `totalCount`, and that the cursor is only base64, not signed, so from reading the code a client can forge one; it only ever selects a position, and an invalid one returns `BAD_USER_INPUT`. A late commit with an older `updated_at` than the consumer's checkpoint would still be missed, so this is not exactly-once.

**Source:** `GolangExercise/offline-sync-app/internal/graph/integration_test.go:180-204`
```go
func TestIntegration_RowUpdatedMidWalkReappearsAndIsNeverSkipped(t *testing.T) {
	_, pool, run := newIntegrationHandler(t, batchSizes{})
	touched := testID(kindLocation, 0)

	got := walk(t, run, func(page int) {
		if page != 0 {
			return
		}
		_, err := pool.Exec(context.Background(), "UPDATE disaster_locations SET updated_at = $1 WHERE id = $2", baseTime.Add(24*time.Hour), touched)
		if err != nil {
			t.Fatalf("touch row: %v", err)
		}
	})

	counts := map[string]int{}
	for _, id := range got {
		counts[id]++
	}
	if len(counts) != nLocations {
		t.Fatalf("distinct rows = %d, want %d: a row was skipped", len(counts), nLocations)
	}
	if counts[touched.String()] != 2 {
		t.Fatalf("updated row seen %d times, want 2: at-least-once delivery, consumer dedups by id", counts[touched.String()])
	}
}
```

**Follow-up they will ask:** Why base64 `updated_at|id` rather than an opaque row number, and could the sort key be something other than `updated_at`?

**A:** A row number would be offset pagination in disguise and would drift under writes, whereas the pair `(updated_at, id)` identifies a position in the sort order itself. The sort key has to be immutable or monotonic for a stable walk, and `updated_at` is neither, which is exactly why a touched row reappears; I accept that because for a sync feed re-delivery is the safe direction, but for a UI list that sorted by `created_at` I would prefer an immutable key. I only built and tested the `updated_at` ordering.

## Phase 4 — Safety: depth and cost limits, and authentication

### 🟢 Beginner

**Q:** Why is a GraphQL API easier to abuse than a REST API?

**A:** In REST each route has a roughly known cost, but in GraphQL the client writes the query, so it can ask for a deeply nested or very wide tree in one request. My schema is even cyclic, because `Location` has `siteAssessments` and `SiteAssessment` has `location`, so a client could nest forever. A DAG schema cannot be deep; it is the back-reference that creates the attack. So I validate depth, size and estimated cost before running anything.

**Q:** How is the API authenticated?

**A:** The handler takes an auth middleware as a parameter and applies it outermost; in production that is the Cognito ID-token verifier, the same one the REST API uses. A missing, garbage, wrong-scheme or expired token gets 401, and the store receives zero calls. Every authenticated user can read every location today, so there is no row-level authorization yet.

### 🟡 Intermediate

**Q:** Explain your layered limits and how cost is calculated.

**A:** The checks run cheapest first: the parser token limit of 5,000, then depth at most 8, then expanded field count at most 1,000, then estimated complexity at most 10,000, then a page-size cap of 100 and a 10-second request timeout. Complexity is estimated rows materialised: scalars cost 0, each object costs 1, `locations` multiplies by `first`, `siteAssessments` assumes 10 per location and `photos` 10 per assessment. I clamp `first` before multiplying because the resolver rejects bad values only after the complexity check has run, and a huge value could overflow into a cheap negative number. Violations return HTTP 422 through `errcode.RegisterErrorType`, because gqlgen's default would answer 200.

**Source:** `GolangExercise/offline-sync-app/internal/graph/limits.go:41-58`
```go
// photos is capped at 10 per site by UpsertPhoto; assessments per location has no cap, so 10 is an estimate.
func complexityRoot() ComplexityRoot {
	var c ComplexityRoot
	c.Query.Locations = func(child int, first *int, _ *string, _ *time.Time) int {
		return clampedPageSize(first) * child
	}
	c.Location.SiteAssessments = func(child int) int { return assumedAssessmentsPerLocation * (child + 1) }
	c.SiteAssessment.Photos = func(child int) int { return maxPhotosPerAssessment * (child + 1) }
	return c
}

// Clamped because the resolver rejects bad values only after the complexity check has already run.
func clampedPageSize(first *int) int {
	if first == nil {
		return DefaultPageSize
	}
	return min(max(*first, 1), MaxPageSize)
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/limits.go:84-110`
```go
// Fragment results are memoised: gqlgen's complexity walk re-expands every spread, so a fragment bomb
// must be rejected here, in linear time, before that walk runs.
func measure(set ast.SelectionSet, memo map[string]shape) shape {
	var out shape
	for _, sel := range set {
		switch s := sel.(type) {
		case *ast.Field:
			if strings.HasPrefix(s.Name, "__") {
				continue
			}
			child := measure(s.SelectionSet, memo)
			out.depth = max(out.depth, 1+child.depth)
			out.fields = min(out.fields+1+child.fields, fieldCountCap)
		case *ast.FragmentSpread:
			child, seen := memo[s.Name]
			if !seen {
				child = measure(s.Definition.SelectionSet, memo)
				memo[s.Name] = child
			}
			out.depth = max(out.depth, child.depth)
			out.fields = min(out.fields+child.fields, fieldCountCap)
		case *ast.InlineFragment:
			child := measure(s.SelectionSet, memo)
			out.depth = max(out.depth, child.depth)
			out.fields = min(out.fields+child.fields, fieldCountCap)
		}
	}
```

I would say that `measure` memoises each fragment by name so a fragment bomb is walked in linear time, and that I wrote it because gqlgen's complexity walk re-expands every spread without memoising.

### 🔴 Senior

**Q:** Defend this design as an abuse defence. What does it stop, what does it not, and what numbers do you have?

**A:** It stops deep cyclic queries, fragment bombs, aliased fan-out and oversized documents, and it rejects them before any resolver or store call runs; the tests assert zero store calls on rejection. The documented numbers are that `first: 50` full nesting costs 5,600 and is accepted, `first: 100` costs 11,200 and is rejected, and 10 aliases of a 1,200 page cost 12,000 and are rejected; the tests assert the accept and reject outcomes, and the arithmetic follows from `complexityRoot`. The deepest legitimate query has depth 7 against a limit of 8, and a 20-hop cycle has depth 42. The constants are policy, not truth: 10 assessments per location is an estimate because nothing caps it, whereas 10 photos per assessment is real because `UpsertPhoto` caps it. Gaps I name plainly are that there is no per-client rate limiting and no persisted-query allowlist, and that I did not test the gqlparser validator itself against fragment bombs, because it runs before my code.

**Source:** `GolangExercise/offline-sync-app/internal/graph/handler.go:34-50`
```go
// auth runs outermost so an unauthenticated request never allocates loaders or touches the store.
func NewHandler(store Store, auth func(http.Handler) http.Handler, cfg ServerConfig) http.Handler {
	srv := handler.New(NewExecutableSchema(Config{
		Resolvers:  &Resolver{Store: store},
		Complexity: complexityRoot(),
	}))
	srv.AddTransport(transport.POST{})
	srv.SetParserTokenLimit(cfg.Limits.MaxTokens)
	srv.SetErrorPresenter(presentError)
	if cfg.Introspection {
		srv.Use(extension.Introspection{})
	}
	srv.Use(queryLimits{cfg.Limits})
	srv.Use(extension.FixedComplexityLimit(cfg.Limits.MaxComplexity, complexity.WithFixedScalarValue(0)))

	return auth(requestScope(store, cfg, srv))
}
```

**Follow-up they will ask:** What about a hostile client that is authenticated and stays under every limit?

**A:** Cost limits bound one request, not a flood of valid ones, so that needs a rate limit per client at the gateway or WAF, which `docs/graphql.md` lists as not covered, and ideally persisted queries so only known documents run. If row-level authorization arrives, it belongs in the `Store` as a SQL `WHERE`, so that loaders cannot bypass it. I have not built either, so I would describe them as the next step, not as a feature.

## Phase 5 — Errors and partial results

### 🟢 Beginner

**Q:** What does a GraphQL error look like, and why can the HTTP status still be 200?

**A:** A GraphQL response has `data` and an optional `errors` array, and each error can carry a `path` to the field that failed. The HTTP layer succeeded, because the server parsed and executed the query, so a field-level failure is not a transport error. In my service parse, validation and limit errors return 422, but a failing child field returns 200 with the rest of the data. The consequence is that monitoring based on status codes alone will miss resolver failures.

### 🟡 Intermediate

**Q:** If the photos query fails, what does the client see, and what do you do with the error?

**A:** The response is 200 with all locations and assessments present, `photos: null`, and one `errors[]` entry per affected path. That works only because `photos` is nullable in the schema; a non-null field would null its nearest nullable parent, up to `data: null`. My error presenter masks resolver errors: an error that has a path and no code is replaced with `internal error` and logged server-side, so SQL text and host names never reach a client. Errors with no path, which are protocol errors, and errors with a code such as `BAD_USER_INPUT` pass through unchanged.

**Source:** `GolangExercise/offline-sync-app/internal/graph/handler.go:65-75`
```go
// Errors without a path are protocol-level (parse, validation, limits) and safe to show; resolver errors carry a path and may embed SQL.
func presentError(ctx context.Context, err error) *gqlerror.Error {
	presented := graphql.DefaultErrorPresenter(ctx, err)
	if len(presented.Path) == 0 || presented.Extensions["code"] != nil {
		return presented
	}
	log.Printf("graphql: resolver error at %v: %s", presented.Path, presented.Message)
	masked := &gqlerror.Error{Message: "internal error", Path: presented.Path}
	errcode.Set(masked, "INTERNAL_SERVER_ERROR")
	return masked
}
```

**Source:** `GolangExercise/offline-sync-app/internal/graph/safety_test.go:253-269`
```go
	if len(resp.Errors) != 6 {
		t.Fatalf("errors = %d, want 6: the shared batch failure surfaces once per assessment", len(resp.Errors))
	}
	for _, e := range resp.Errors {
		if len(e.Path) != 7 || e.Path[0] != "locations" || e.Path[len(e.Path)-1] != "photos" {
			t.Errorf("error path = %v, want locations.edges[i].node.siteAssessments[j].photos", e.Path)
		}
		if e.Message != "internal error" || strings.Contains(e.Message, "hunter2") {
			t.Errorf("message = %q, want the masked message", e.Message)
		}
		if e.Extensions["code"] != "INTERNAL_SERVER_ERROR" {
			t.Errorf("code = %v, want INTERNAL_SERVER_ERROR", e.Extensions["code"])
		}
	}
	if got := store.callCount("PhotosBySiteAssessmentIDs"); got != 1 {
		t.Errorf("photo batch calls = %d, want 1: failure is one batch, not six fetches", got)
	}
```

I would say that the test seeds a fake password into the store error and asserts it never appears in the response, which is how I prove the masking is real and not just intended.

### 🔴 Senior

**Q:** What are the sharp edges of partial results, and how do you reason about nullability?

**A:** Nullability is the reliability contract: every nullable child is a promise that its failure degrades one path, and every non-null field is a promise that its failure may erase its parent. One failed batch is one query but N errors, one per waiting field; my test shows 6 errors from a single photos batch call, and the response is still 200. `Query.locations` is non-null on purpose, because if the root list fails there is nothing to return, and the test shows `data: null` with exactly one masked error. A resolver must return an error rather than panic, because gqlgen nulls the entire list when an element panics. The masking rule is a heuristic keyed on path and code, so any resolver error that someone tags with a code would pass through to the client, and today only `BAD_USER_INPUT` is used that way. I asserted these behaviours with a fake store; I have not measured error rates, and I have not built any metric on the presenter.

**Source:** `GolangExercise/offline-sync-app/internal/graph/safety_test.go:289-301`
```go
func TestRootFailureNullsDataAndReportsOneMaskedError(t *testing.T) {
	store := newFakeStore(2, 0, 0)
	store.failOn["ListLocations"] = errors.New("connection refused to 10.0.0.5:5432")

	resp := post(t, newTestHandler(store), `{ locations { edges { cursor } } }`, nil)

	if len(resp.Errors) != 1 || resp.Errors[0].Message != "internal error" {
		t.Fatalf("errors = %+v, want exactly one masked error", resp.Errors)
	}
	if string(resp.Data) != "null" {
		t.Errorf("data = %s, want null because locations is non-null", resp.Data)
	}
}
```

**Follow-up they will ask:** If every error is HTTP 200, how do you monitor this API?

**A:** The presenter already logs the real error with its path, so the first step would be to emit a counter from `presentError` labelled by path and code and alert on its rate, plus status-code alerts for the 422 limit violations that I deliberately made visible to gateways. That is a design, not something I built: today the presenter only logs, and there are no metrics or tracing in this service.

## Phase 6 — Performance and the supporting index (EXPLAIN)

### 🟢 Beginner

**Q:** What is an index, and why does keyset pagination need one?

**A:** An index is a sorted structure, a B-tree in Postgres, that lets the database find rows by key without reading the whole table. Keyset pagination asks for the rows after a given position in a given order, and without an index the database must scan and sort the table for every page. With an index in the same order as the query, it seeks to the position and reads only the page.

### 🟡 Intermediate

**Q:** What index did you add, and how did you prove it is used?

**A:** I added a B-tree on `disaster_locations (updated_at, id)`, in the same column order as the `ORDER BY` and the row comparison, so one seek serves both the filter and the order. I created it `CONCURRENTLY` so that it does not block writes while it builds, which means it cannot run inside a transaction and has to be the only statement in the migration. To prove it, I ran `EXPLAIN (ANALYZE, BUFFERS)` on the second-page query against 100,000 seeded rows inside a rolled-back transaction, once with the index and once with it dropped in the same transaction.

**Source:** `GolangExercise/offline-sync-app/migrations/000004_locations_updated_at_id_idx.up.sql:1-2`
```sql
-- CONCURRENTLY does not block writes during the build, but cannot run inside a transaction: keep it the only statement here.
CREATE INDEX CONCURRENTLY disaster_locations_updated_at_id_idx ON disaster_locations (updated_at, id);
```

**Illustrative (not from the repo):**
```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM disaster_locations
WHERE updated_at >= $1 AND (updated_at, id) > ($2, $3)
ORDER BY updated_at, id LIMIT 51;
```

This is the shape of the check; I did not run this exact statement in this session, and the recorded results are in `docs/graphql.md`. I would say what to look for: an `Index Scan` with both predicates in `Index Cond`, a small `Buffers: shared hit` count, and no `Sort` node.

### 🔴 Senior

**Q:** Give me the numbers and tell me what they do and do not prove.

**A:** The recorded run shows an `Index Scan` on `disaster_locations_updated_at_id_idx` returning 51 rows with 4 shared buffers in 0.037 ms. With the index dropped in the same transaction, the plan became a parallel sequential scan plus a top-N heapsort, with 27,024 rows removed by the filter per loop, 2,485 shared buffers and 19.2 ms. That is roughly 600 times fewer buffers, but it is one local run on synthetic data in one Postgres instance, not a repeated benchmark and not production data. Also on the 50 rows that the integration tests leave behind, the planner chooses `Seq Scan` plus `Sort`, which is correct for a one-page table, so an EXPLAIN on a tiny dev table proves nothing about index use. The failure mode of `CREATE INDEX CONCURRENTLY` is that a failure midway leaves an `INVALID` index which must be dropped before a retry. The cost on the write side is that every update of `updated_at` now touches this index; I reason that this is acceptable for a read-heavy feed, but I did not measure write amplification.

**Source:** `GolangExercise/offline-sync-app/internal/graph/pgstore.go:37-50`
```go
func (s *PostgresStore) LocationsByIDs(ctx context.Context, ids []uuid.UUID) ([]db.DisasterLocation, error) {
	return collect(ctx, s.conn, pgx.RowToStructByPos[db.DisasterLocation],
		"SELECT "+locationCols+" FROM disaster_locations WHERE id = ANY($1)", ids)
}

func (s *PostgresStore) SiteAssessmentsByLocationIDs(ctx context.Context, ids []uuid.UUID) ([]db.SiteAssessment, error) {
	return collect(ctx, s.conn, pgx.RowToStructByPos[db.SiteAssessment],
		"SELECT "+assessmentCols+" FROM site_assessments WHERE location_id = ANY($1) ORDER BY created_at, id", ids)
}

func (s *PostgresStore) PhotosBySiteAssessmentIDs(ctx context.Context, ids []uuid.UUID) ([]db.Photo, error) {
	return collect(ctx, s.conn, pgx.RowToStructByPos[db.Photo],
		"SELECT "+photoCols+" FROM photos WHERE site_assessment_id = ANY($1) ORDER BY created_at, id", ids)
}
```

**Follow-up they will ask:** Do the batched `= ANY($1)` queries have supporting indexes too?

**A:** From reading `migrations/000001_init_schema.up.sql`, `site_assessments(location_id)` and `photos(site_assessment_id)` both have indexes, which are the columns those two batch queries filter on, but I did not run EXPLAIN on those queries, so I would say they are likely served by the indexes and that I have not verified it. `MaxBatch` of 500 bounds the size of each `ANY` list, and I have not measured how the planner behaves at that size.

## Phase 7 — Designing an API a partner can safely sync from

### 🟢 Beginner

**Q:** What does a partner need from an API to sync data safely?

**A:** The partner needs to fetch only what changed since its last run, in stable pages, without losing or duplicating rows. That means an `updated_since` filter, a cursor for paging within one run, and a stable id so the partner can deduplicate. It also needs to learn about deletes, and a way to retry a write safely. Finally, the server should tell it to slow down when it calls too fast.

**Q:** What is an idempotency key?

**A:** It is a client-chosen token sent with a write so that if the request is retried, the server returns the first result instead of applying the change twice. In my two-way sync, the push to the partner carries the domain event id as the `Idempotency-Key`. If the first call succeeded but its response was lost, the retry replays the original answer instead of writing twice.

### 🟡 Intermediate

**Q:** Show me the pull side: how do cursor and `updated_since` combine?

**A:** My mock partner API lists issues keyset-paginated on `(UpdatedAt, ID)`, takes `updated_since` as RFC 3339 and a `cursor`, and returns `nextCursor` which is empty on the last page. The filter is inclusive and the cursor continues strictly after the last position. On my side the extractor starts an incremental run at the stored watermark minus an overlap window, so late commits and timestamp granularity cannot cause skips, and then applies each page and its checkpoint in one transaction. The re-reads that the overlap causes are free because applying an already-seen version is a no-op through the version gate.

**Source:** `GolangExercise/offline-sync-app/internal/mockjira/mockjira.go:172-201`
```go
// List is keyset-paginated on (UpdatedAt, ID); tombstones are included so an
// incremental pull can see deletes.
func (s *Server) List(since time.Time, cursor string, limit int) (Page, error) {
	after, err := decodeCursor(cursor)
	if err != nil {
		return Page{}, err
	}

	s.mu.Lock()
	matching := make([]Issue, 0, len(s.issues))
	for _, issue := range s.issues {
		if issue.UpdatedAt.Before(since) {
			continue
		}
		if cursor != "" && !after.before(*issue) {
			continue
		}
		matching = append(matching, *issue)
	}
	s.mu.Unlock()

	sort.Slice(matching, func(i, j int) bool { return less(matching[i], matching[j]) })

	page := Page{Issues: matching}
	if limit > 0 && len(matching) > limit {
		page.Issues = matching[:limit]
		page.NextCursor = encodeCursor(page.Issues[limit-1])
	}
	return page, nil
}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/extractor.go:61-68`
```go
	since, cursor, runMax := state.RunSince.Time, state.NextCursor, state.RunMax
	if cursor == "" {
		since = time.Time{}
		if state.Watermark.Valid {
			since = state.Watermark.Time.Add(-e.cfg.Overlap)
		}
		runMax = state.Watermark
	}
```

**Illustrative (not from the repo):**
```go
func Pull(fetch FetchPage, watermark time.Time, overlap time.Duration, apply func(Node)) (time.Time, error) {
	since := watermark.Add(-overlap)
	newMark := watermark
	after := ""
	for {
		page, err := fetch(since, after)
		if err != nil {
			return watermark, err
		}
		for _, n := range page.Nodes {
			apply(n)
			if n.UpdatedAt.After(newMark) {
				newMark = n.UpdatedAt
			}
		}
		if !page.HasNextPage {
			return newMark, nil
		}
		after = page.EndCursor
	}
}
```

This loop was compiled and run against a toy in-memory fetcher in the scratchpad, not against the repo. I would say that the watermark only advances after the last page, that `apply` must be idempotent because the overlap deliberately re-delivers, and that the real extractor additionally commits a checkpoint per page so a crash resumes from the cursor.

### 🔴 Senior

**Q:** Design the full contract for a partner-facing sync API and be honest about what my code covers.

**A:** The contract is a monotonic version plus `updatedAt` per record, a keyset cursor on `(updatedAt, id)`, an inclusive `updated_since`, a bounded page size, tombstones for deletes, idempotency keys on writes, and 429 with `Retry-After` for rate limits, with webhooks for the push half and a poll as the repair path. In the mock partner API, delete sets a `Deleted` flag, bumps the version and keeps the row, and the list includes tombstones, so an incremental pull can see deletes; a missing row in a poll is never treated as a delete, and a test asserts an empty poll deletes nothing. On the consumer side, `delay()` honours `Retry-After` when it is present and otherwise uses full-jitter exponential backoff. The honest gaps are these: my GraphQL schema has no tombstones and no version field, so deletes cannot be synced through it, and a partner cannot order conflicting changes by version there, only by `updatedAt`. The mock's idempotency map is unbounded, has no expiry and does not check that a repeated key carries the same body, and its `limit` of zero returns everything, so a real API must cap the page size. The mock has no real rate limiter, only on-demand 429 fault injection, and the GraphQL service has no per-client limiter either. Late commits older than the overlap are missed unless there is a periodic full reconcile, which I did not build.

**Source:** `GolangExercise/offline-sync-app/internal/mockjira/handler.go:92-111`
```go
// patch replays the stored response for a repeated Idempotency-Key instead of
// applying the change (and bumping the version) a second time.
func (s *Server) patch(id string, p Patch, key string) (Issue, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.patchCalls++
	if key != "" {
		if prior, ok := s.idempotent[key]; ok {
			return prior, nil
		}
	}
	issue, err := s.update(id, p)
	if err != nil {
		return Issue{}, err
	}
	if key != "" {
		s.idempotent[key] = issue
	}
	return issue, nil
}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/client.go:140-153`
```go
// delay honours the server's Retry-After when it sent one, otherwise full
// jitter: a uniform draw from [0, min(MaxDelay, BaseDelay * 2^(attempt-1))].
func (c *HTTPClient) delay(attempt int, err error) time.Duration {
	var api *APIError
	if errors.As(err, &api) && api.RetryAfter > 0 {
		return api.RetryAfter
	}
	ceiling := c.policy.BaseDelay
	for i := 1; i < attempt && ceiling < c.policy.MaxDelay; i++ {
		ceiling *= 2
	}
	ceiling = min(ceiling, c.policy.MaxDelay)
	return time.Duration(c.rand() * float64(ceiling))
}
```

**Follow-up they will ask:** How would you add tombstones to the GraphQL feed?

**A:** I would soft-delete rows with a nullable `deletedAt`, keep them in the `(updated_at, id)` feed so a delete is just another update that moves the row forward, and expose that field so the consumer can apply it as a delete. I would also expose a monotonic `version` so the partner can order changes without trusting clocks, and add a retention policy for old tombstones. This is a design only: none of it exists in the schema today.

**Illustrative (not from the repo):**
```graphql
type Location {
  id: ID!
  version: Int!
  updatedAt: Time!
  deletedAt: Time
}
```

## Code reference index

| path:lines | what it shows |
|---|---|
| `GolangExercise/offline-sync-app/internal/graph/schema.graphqls:9-48` | Query, connection types, `Location` and the cyclic `SiteAssessment.location` |
| `GolangExercise/offline-sync-app/internal/graph/dataloader.go:43-76` | `Load` and `enqueue`: mutex, per-key cache, timer and size flush |
| `GolangExercise/offline-sync-app/internal/graph/dataloader.go:91-100` | `run` recovers panics on the timer goroutine |
| `GolangExercise/offline-sync-app/internal/graph/loaders.go:18-97` | Batch functions, `indexBy`/`groupBy`, per-request context wiring |
| `GolangExercise/offline-sync-app/internal/graph/schema.resolvers.go:16-22` | A four-line resolver that delegates to the loader |
| `GolangExercise/offline-sync-app/internal/graph/nplusone_test.go:53-91` | Asserted 3 batched versus 201 naive store calls |
| `GolangExercise/offline-sync-app/internal/graph/cursor.go:16-40` | Keyset cursor encode and decode |
| `GolangExercise/offline-sync-app/internal/graph/pgstore.go:65-88` | Keyset SQL with row comparison and bind arguments |
| `GolangExercise/offline-sync-app/internal/graph/integration_test.go:158-204` | Tie-breaking on `id` and the mid-walk update re-delivery |
| `GolangExercise/offline-sync-app/internal/graph/limits.go:14-112` | Limits, complexity estimates, memoised `measure` |
| `GolangExercise/offline-sync-app/internal/graph/handler.go:26-75` | Server config, auth outermost, request scope, `presentError` |
| `GolangExercise/offline-sync-app/internal/graph/safety_test.go:139-185` | Complexity accept and reject, alias multiplication |
| `GolangExercise/offline-sync-app/internal/graph/safety_test.go:215-301` | Partial results, masked errors, root failure |
| `GolangExercise/offline-sync-app/internal/graph/authn_test.go:94-141` | 401 before any store call |
| `GolangExercise/offline-sync-app/cmd/graphql/main.go:29-47` | Wiring: introspection only when local, auth verifier, timeouts |
| `GolangExercise/offline-sync-app/migrations/000004_locations_updated_at_id_idx.up.sql:1-2` | The `CONCURRENTLY` index on `(updated_at, id)` |
| `GolangExercise/offline-sync-app/docs/graphql.md:101-130` | Keyset rationale and the recorded EXPLAIN numbers |
| `GolangExercise/offline-sync-app/docs/graphql.md:132-157` | Limits table with the 5,600 and 11,200 figures |
| `GolangExercise/offline-sync-app/internal/mockjira/mockjira.go:172-201` | Keyset list with `updated_since` and tombstones |
| `GolangExercise/offline-sync-app/internal/mockjira/handler.go:92-111` | Idempotency-key replay |
| `GolangExercise/offline-sync-app/internal/twoway/extractor.go:53-112` | Resumable pull with overlap and per-page checkpoint |
| `GolangExercise/offline-sync-app/internal/twoway/client.go:140-153` | `Retry-After` or full-jitter backoff |
| `GolangExercise/offline-sync-app/docs/two-way-sync.md` | Why each sync choice, and the "What is NOT solved" list |

## Self-check

1. **Q:** Why does the naive nested query cost 201 store calls and the DataLoader version 3? **A:** Because 1 list plus 50 per-location plus 150 per-assessment queries collapse into one query per nesting level.
2. **Q:** Why is `id` part of the cursor? **A:** Many rows can share one `updated_at`, and without `id` as a tiebreaker rows at a page boundary are lost or repeated.
3. **Q:** Why does the limit check run before the complexity walk? **A:** A fragment bomb would make gqlgen's non-memoised complexity walk slow, so the memoised depth and field walk rejects it in linear time first.
4. **Q:** Why is `photos` nullable? **A:** So a failed photos batch nulls only that path and leaves the parent data and siblings intact.
5. **Q:** Why does the extractor start an overlap before the watermark? **A:** To avoid skipping late commits and timestamp-boundary rows, which is safe because replays are no-ops through the version gate.

## What not to claim

- Do not claim GraphQL is faster than REST; I measured query counts and one plan, not a latency comparison.
- Do not claim the 2 ms window cost, the loader versus `dataloadgen`, or write amplification of the index was measured; none was.
- Do not claim the EXPLAIN result is production evidence; it is one local run on 100,000 synthetic rows.
- Do not claim the schema supports deletes: there are no tombstones and no version field in the GraphQL schema.
- Do not claim fragment-bomb validation is fully tested; I did not test the gqlparser validator itself.
- Do not claim rate limiting, persisted queries or row-level authorization exist; they do not.
- Do not claim the mutation-run figures (15 of 50 rows lost, 201 versus 3 on `MaxBatch` 1) were re-run for this guide; they are recorded in `docs/graphql.md`.
- Do not describe `mockjira` as Jira; its payloads, headers and pagination are invented for tests.
- Do not claim exactly-once; the design is at-least-once with idempotent apply.
