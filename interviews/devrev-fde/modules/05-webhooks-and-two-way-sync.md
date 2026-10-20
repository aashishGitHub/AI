# Module 05 — Webhooks & two-way sync

> This module is the part of the interview where DevRev's core product, AirSync (data sync between a customer's tools and DevRev), meets code I actually wrote. The code lives in `GolangExercise/offline-sync-app` (packages `internal/webhook`, `internal/twoway`, `internal/mockjira`), plus portable drills in `AI/interviews/devrev-fde/drills`. Lanes: everything in this module is **[L]** (my own build) and it runs against a **mock** Jira that I wrote, never a real vendor; the one **[P]** (shipped at Couchbase) item is the Workato/NetSuite integration in Phase 8, which was request/response and not a webhook or two-way sync. DevRev facts below come from README section 1, which I verified against developer.devrev.ai on 2026-10-19; docs change, so re-check them the week of the interview. I use DevRev's current words, "extraction" and "data loading", not "extractor" and "loader" (those are my package names, not DevRev terms).

Verified on 2026-10-20: `go test ./internal/webhook ./internal/twoway ./internal/mockjira ./cmd/webhook-receiver-lambda` passes (68 PASS lines, subtests included), and `go test -tags=integration -run Integration ./internal/twoway/` passes all 15 integration tests against a local Postgres 16 container.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Receive and verify a webhook | Prove the bytes came from the sender, were not altered, are fresh, and carry the delivery id the sender signed. | `internal/webhook/verify.go`, `handler.go` |
| 2. Inbox, dedupe and acknowledging fast (202) | Store the raw event atomically, answer 202, and let a worker apply it later. | `internal/webhook/handler.go`, `worker.go`, `webhook_inbox` |
| 3. Identity mapping | Turn an external id into a stable internal id exactly once, even under races. | `internal/twoway/apply.go` (`ResolveInternalID`), `external_id_map` |
| 4. Deciding what wins | Field ownership, external version gate, last-write-wins contrast, and echo-loop prevention. | `internal/twoway/ownership.go`, `apply.go` |
| 5. Loading changes back | Push internal edits out with an idempotency key, honouring 429 and backing off with jitter. | `internal/twoway/loader.go`, `client.go` |
| 6. Resumable backfill under a time budget | Pull history page by page, checkpoint with each page, and stop cleanly before a time limit. | `internal/twoway/extractor.go`, `sync_state` |
| 7. Deletes, dead letters and reconciliation | Tombstone deletes, park poison messages, and know what drift detection is missing. | `queries.sql`, `worker.go`, `sync_dead_letters` |
| 8. Third-party integration lessons and the DevRev AirSync mapping | Tell the Workato story honestly and map my build onto AirSync's concepts. | `STAR.md` story 1, `README.md` section 1 |

---

## Phase 1 — Receive and verify a webhook (raw bytes, HMAC, constant-time, timestamp window, signed delivery id)

### 🟢 Beginner

**Q:** What is a webhook, and why does a receiver have to verify it?

**A:** A webhook is the other system calling a URL of mine when something changes, instead of me asking it over and over. Because that URL is public, anybody on the internet can POST to it, so I need proof that the sender holds a secret we share. In my implementation the sender computes an HMAC-SHA256, which is a hash keyed by the shared secret, over the request, and I recompute it on my side. If the two match, the body was not altered and the sender knows the secret. I also never treat webhooks as complete, because they can be dropped, duplicated or reordered, so a poll runs underneath as the safety net.

### 🟡 Intermediate

**Q:** Walk me through your verify function. What exactly is signed, and why those details?

**A:** In my implementation the signed string is the timestamp, a dot, the delivery id, a dot, and then the raw request body bytes, and the signature header looks like `sha256=<hex>`. I verify against the exact bytes I received, because parsing the JSON and re-encoding it changes whitespace or key order and therefore the MAC; a test signs a body with odd spacing to prove the point. I decode the hex signature and compare bytes with `hmac.Equal`, which is a constant-time compare, so I do not leak how many leading bytes matched the way `==` on strings can. The timestamp is inside the MAC and I reject anything more than five minutes away in either direction, which bounds replay of a captured request. Finally I reject a delivery id that contains a dot, because the dot is my separator and without that rule a captured request could shift body bytes into the id and keep a valid MAC.

**Source:** `GolangExercise/offline-sync-app/internal/webhook/verify.go:44-47`

```go
	hexSig, ok := strings.CutPrefix(signature, signaturePrefix)
	// A "." in the id would let a captured request shift body bytes into the id and keep a valid MAC.
	if !ok || timestamp == "" || strings.Contains(deliveryID, ".") {
		return ErrMalformedHeaders
```

**Source:** `GolangExercise/offline-sync-app/internal/webhook/verify.go:58-70`

```go
	mac := hmac.New(sha256.New, v.secret)
	mac.Write([]byte(timestamp + "." + deliveryID + "."))
	mac.Write(body)
	if !hmac.Equal(got, mac.Sum(nil)) {
		return ErrBadSignature
	}

	age := v.now().Sub(time.Unix(secs, 0))
	if age > v.tolerance || age < -v.tolerance {
		return ErrStaleTimestamp
	}
	return nil
}
```

**How to talk about it:** I point at three lines: the dot check on the id, `hmac.Equal` on decoded bytes, and that the window check comes after the MAC check. The TypeScript drill in `drills/ts/src/webhook.ts` is a simpler `timestamp.body` scheme that checks the window first and returns typed reasons; I say which of the two I am describing so nobody thinks the drill signs the delivery id.

### 🔴 Senior

**Q:** Your verify passes its tests. What attacks are still open, what does verification cost, and what did you actually measure?

**A:** The open ones are these. An exact replay of the same timestamp, id and body inside the five-minute window still verifies, but it lands on the inbox primary key and becomes a harmless `202 duplicate`. There is no secret rotation, because there is a single secret and no dual-verify window. On the Lambda variant the secret is passed as an environment variable, so anyone with `lambda:GetFunctionConfiguration` can read it; fetching it from Secrets Manager at cold start is the stronger option and I did not build it. On cost, I benchmarked a copy of `verify.go` in a scratch module on an Apple M2 Pro: about 0.93 microseconds for a 1 KiB body and about 0.44 milliseconds for a 1 MiB body, which is the default body cap. That is an in-memory micro-benchmark, not a Lambda or a network measurement, so it says verification is not the bottleneck and nothing more. The boundary of the claim is that the mock vendor signs with my own scheme, so a self-consistent mistake would pass; the guard is a test vector produced with `openssl dgst -sha256 -hmac`, which both the verifier and the mock check against. A real vendor's header names and signing recipe will differ, and from memory the Standard Webhooks spec signs `id.timestamp.body`, which you should verify before quoting.

The reason the delivery id is signed is the most interesting design decision, and a test pins it.

**Source:** `GolangExercise/offline-sync-app/internal/webhook/handler_test.go:103-120`

```go
func TestHandler_DeliveryIDSwappedAfterSigningIs401SoTheRealDeliveryIsNotSwallowed(t *testing.T) {
	inbox := newFakeInbox()
	h := newTestHandler(inbox)
	captured := `{"issue":{"id":"MJ-1"},"version":1}`
	ts, sig := signAt(testNow, "dlv-1", captured)

	forged := post(h, "dlv-2", ts, sig, captured)

	if forged.Code != http.StatusUnauthorized || !strings.Contains(forged.Body.String(), "bad_signature") || len(inbox.rows) != 0 {
		t.Fatalf("forged id: got %d %s with %d stored, want 401 bad_signature and nothing stored", forged.Code, forged.Body.String(), len(inbox.rows))
	}
	genuine := `{"issue":{"id":"MJ-1"},"version":2}`
	ts, sig = signAt(testNow, "dlv-2", genuine)
	w := post(h, "dlv-2", ts, sig, genuine)
	if w.Code != http.StatusAccepted || !strings.Contains(w.Body.String(), "accepted") || string(inbox.rows["mockjira/dlv-2"]) != genuine {
		t.Errorf("genuine dlv-2: got %d %s, stored %q, want 202 accepted with its own body", w.Code, w.Body.String(), inbox.rows["mockjira/dlv-2"])
	}
}
```

The squatting attack in two lines of arithmetic, with and without the id inside the MAC:

**Illustrative (not from the repo):**

```python
import hashlib
import hmac


def mac(secret: bytes, *parts: bytes) -> str:
    return hmac.new(secret, b".".join(parts), hashlib.sha256).hexdigest()


def accepts(secret, ts, body, claimed_id, sig, signs_id):
    parts = (ts, claimed_id, body) if signs_id else (ts, body)
    return hmac.compare_digest(sig, mac(secret, *parts))


secret, ts = b"whsec", b"1700000000"
body = b'{"issue":{"id":"MJ-1"},"version":1}'

captured_unsigned_id = mac(secret, ts, body)
captured_signed_id = mac(secret, ts, b"dlv-42", body)
print(accepts(secret, ts, body, b"dlv-43", captured_unsigned_id, signs_id=False))
print(accepts(secret, ts, body, b"dlv-43", captured_signed_id, signs_id=True))
```

**Follow-up they will ask:** "How would you rotate the webhook secret without dropping deliveries?"

**A:** I would accept signatures from both the old and the new secret for an overlap window, then retire the old one once the vendor confirms it switched. The loop must not return early on the first match, so the timing does not reveal which secret matched, and I would log which secret verified so I can see when the old one goes quiet. This is not built in my repo, the snippet below is a sketch I ran in isolation, and the drill write-up lists the same idea under secret rotation.

**Illustrative (not from the repo):**

```python
import hashlib
import hmac


def verify_any(secrets: list[bytes], message: bytes, got: bytes) -> bool:
    ok = False
    for secret in secrets:
        ok |= hmac.compare_digest(hmac.new(secret, message, hashlib.sha256).digest(), got)
    return ok


message, old, new = b"1700000000.dlv-1.{}", b"old-secret", b"new-secret"
signed_with_old = hmac.new(old, message, hashlib.sha256).digest()
print(verify_any([new, old], message, signed_with_old))
print(verify_any([new], message, signed_with_old))
```

---

## Phase 2 — Inbox, dedupe and acknowledging fast (202)

### 🟢 Beginner

**Q:** Why does the receiver answer 202 quickly instead of doing the work inside the request?

**A:** The sender only needs to hear that I stored its event, so I authenticate it, write it down, and answer straight away. If I did the real work inside the request, the sender's retry policy would be tied to my database health and my slowest handler, and a bad body would be retried by them forever. I call the stored row an inbox, and a separate worker processes it afterwards at my own pace. The price is that the data is eventually consistent, so I have to be clear about that with customers.

### 🟡 Intermediate

**Q:** How does your inbox dedupe, and what status codes does the handler return?

**A:** The inbox table's primary key is the system plus the delivery id, and the insert is `ON CONFLICT DO NOTHING`, so "have I seen this" and "is the raw event stored" are one atomic statement and cannot disagree. A first delivery inserts one row and gets `202 accepted`; a repeat inserts zero rows and also gets `202 duplicate`, because the sender must stop retrying and the first copy is already stored. A body over the cap is `413`, an unreadable body is `400`, a failed verification is `401` and nothing is written, a missing delivery id is `400`, and a database failure is `500` so that the sender does retry. I authenticate before touching the database, so unauthenticated traffic never costs a row.

**Source:** `GolangExercise/offline-sync-app/internal/webhook/handler.go:58-62`

```go
		if err := verifier.Verify(r.Header.Get(HeaderTimestamp), deliveryID, r.Header.Get(HeaderSignature), body); err != nil {
			log.Printf("webhook %s: rejected delivery %q: %v", system, deliveryID, err)
			reply(w, http.StatusUnauthorized, rejectionCode(err))
			return
		}
```

**Source:** `GolangExercise/offline-sync-app/internal/webhook/handler.go:69-79`

```go
		inserted, err := inbox.Insert(r.Context(), system, deliveryID, body)
		if err != nil {
			log.Printf("webhook %s: persist delivery %s: %v", system, deliveryID, err)
			reply(w, http.StatusInternalServerError, "inbox_unavailable")
			return
		}
		if !inserted {
			reply(w, http.StatusAccepted, "duplicate")
			return
		}
		reply(w, http.StatusAccepted, "accepted")
```

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:201-205`

```sql
-- name: InsertWebhookInbox :execrows
-- 1 row = first delivery, 0 rows = duplicate delivery id.
INSERT INTO webhook_inbox (system, delivery_id, body)
VALUES ($1, $2, $3)
ON CONFLICT (system, delivery_id) DO NOTHING;
```

**How to talk about it:** I say that the 202 for a duplicate and the 500 for a database failure are the two deliberate choices: one stops retries, the other asks for them. The same router is mounted by `cmd/webhook-receiver` and by the Lambda entrypoint, so the two runtimes cannot drift.

### 🔴 Senior

**Q:** The sender retries aggressively and sometimes sends garbage. How does your worker behave under a database blip or a poison body, and how fast can it drain?

**A:** The worker takes pending rows in batches of 25, and for each row it opens one transaction, claims the row with `FOR UPDATE SKIP LOCKED`, runs the processor, marks the row processed, and commits, so a crash means nothing happened and two workers never take the same row. A failing row does not block the batch: its attempt count goes up in a separate transaction, and at the maximum it is copied to `sync_dead_letters` as raw bytes and marked dead. In the integration test a body that is not JSON is dead-lettered after exactly three attempts, because the test configures three; the shipped default from `SYNC_MAX_ATTEMPTS` is five. The failure mode I name myself is that inbox retries have no backoff beyond the tick interval, and a poison body burns the same attempts as a transient database error. On drain rate, the local process ticks every two seconds with a batch of 25, so the ceiling is about 12.5 deliveries per second per worker; that is derived from the constants and I did not measure it, and in production I would make the worker queue-triggered rather than ticker-driven. The boundary of the claim: the Lambda was never applied to AWS, and deployed alone it would fill `webhook_inbox` while nothing drained it, because the worker only runs inside `cmd/webhook-receiver`.

**Source:** `GolangExercise/offline-sync-app/internal/webhook/worker.go:71-90`

```go
	row, err := q.ClaimInboxRow(ctx, db.ClaimInboxRowParams{System: w.system, DeliveryID: deliveryID})
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("claim inbox row: %w", err)
	}

	outcome, err := w.process(ctx, q, row.Body)
	if err != nil {
		return false, err
	}
	if err := q.MarkInboxProcessed(ctx, db.MarkInboxProcessedParams{System: w.system, DeliveryID: deliveryID, Outcome: outcome}); err != nil {
		return false, fmt.Errorf("mark inbox processed: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return false, fmt.Errorf("commit tx: %w", err)
	}
	return true, nil
}
```

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:213-216`

```sql
-- name: ClaimInboxRow :one
SELECT * FROM webhook_inbox
WHERE system = $1 AND delivery_id = $2 AND processed_at IS NULL AND dead_at IS NULL
FOR UPDATE SKIP LOCKED;
```

**Follow-up they will ask:** "Why a Postgres inbox and not a queue in front?"

**A:** Because one `INSERT ... ON CONFLICT DO NOTHING` gives me dedupe and the durable raw event in one atomic step, and the applied change, the domain event and the processed mark can commit in the same transaction as the work. A queue such as SQS would need its own dedupe story, and I am not certain of the exact FIFO dedupe window, so verify it before quoting. The cost is that I own retention (there is no cleanup job for `webhook_inbox` yet) and the polling or triggering of the worker.

---

## Phase 3 — Identity mapping (external id to internal id)

### 🟢 Beginner

**Q:** What is identity mapping, and why do you need it in a sync?

**A:** The other system calls a record `MJ-1` and my system calls the same record by a UUID, so I keep a table that says which is which. Without it I could not tell whether an incoming event is a new record or an update to one I already have, and I would create duplicates. In my build the table is `external_id_map`, keyed by the system name plus the external id. The first time I see an external id I mint an internal id and store the pair, and every later event for that record finds the same internal id.

### 🟡 Intermediate

**Q:** How do you get the internal id for an external id safely when two workers might see it for the first time at the same moment?

**A:** I insert first and select second. The insert is `ON CONFLICT DO NOTHING` on the primary key `(system, external_id)`, so if another transaction inserted the same key, mine blocks until that one commits and then does nothing. Then I select the row and use whatever id is stored, which is the winner's id, not the one I minted. The code comment says this is race-safe under READ COMMITTED, and an integration test fires eight concurrent first sights of one external id and asserts exactly one link, one work item and one `applied` outcome. The link row also carries `last_version`, because the version is a property of one external system's copy of the record, so a second system would get its own link and its own version.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/apply.go:141-150`

```go
func ResolveInternalID(ctx context.Context, q db.Querier, system, externalID string, newID func() uuid.UUID) (uuid.UUID, error) {
	if err := q.InsertExternalLink(ctx, db.InsertExternalLinkParams{System: system, ExternalID: externalID, InternalID: newID()}); err != nil {
		return uuid.Nil, fmt.Errorf("insert link %s/%s: %w", system, externalID, err)
	}
	link, err := q.GetExternalLink(ctx, db.GetExternalLinkParams{System: system, ExternalID: externalID})
	if err != nil {
		return uuid.Nil, fmt.Errorf("get link %s/%s: %w", system, externalID, err)
	}
	return link.InternalID, nil
}
```

**Source:** `GolangExercise/offline-sync-app/migrations/000003_two_way_sync.up.sql:13-20`

```sql
CREATE TABLE external_id_map (
    system       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    internal_id  UUID NOT NULL,
    last_version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (system, external_id),
    UNIQUE (system, internal_id)
);
```

**How to talk about it:** I say that the reverse index, `UNIQUE (system, internal_id)`, is what the loader uses to find the external id when an internal edit has to be pushed out. I also admit the table has no `entity_type` and no foreign key to `work_items`, on purpose, and that I would add `entity_type` before supporting a second entity.

### 🔴 Senior

**Q:** The mapping lookup fails with a transient error. What must the code not do, and where are the edges of your design?

**A:** It must not treat "the lookup failed" as "the record does not exist", because then it mints a second internal id for a record it already has, and now there are two. In my code any error from the select is returned as an error and the page or delivery is retried; only a successful insert-then-select ever yields an id. DevRev's mapper documentation says the same thing for `getByExternalId`: it returns null when the mapping is missing, other failures throw `AirSyncHttpError`, and a connector must never convert a transient failure into "not found" (README section 1). The failure modes I know of in my design are these. There is no `entity_type` in the key, so two entity types with the same external id would collide. `ResolveInternalID` generates a fresh UUID on every call even when a link already exists, which wastes a little work; I have not measured it and I expect it to be negligible next to a database round trip. The loader skips a work item that has no external link, so creating a record on the internal side and pushing it out is not built. The boundary of the claim is one entity type against one mock system.

The same discipline as a generic sketch with a deliberately flaky store, ran in isolation. The store interface is mine and is not the DevRev SDK's signature:

**Illustrative (not from the repo):**

```python
class TransientError(Exception):
    pass


def resolve(store, external_id, new_id):
    found = store.get_by_external_id(external_id)
    if found is not None:
        return found
    internal_id = new_id()
    store.create(external_id, internal_id)
    return internal_id


class FlakyStore:
    def __init__(self):
        self.rows = {"MJ-1": "item-1"}
        self.fail_next_read = True

    def get_by_external_id(self, external_id):
        if self.fail_next_read:
            self.fail_next_read = False
            raise TransientError("503 from mapper service")
        return self.rows.get(external_id)

    def create(self, external_id, internal_id):
        self.rows[external_id] = internal_id


store = FlakyStore()
try:
    resolve(store, "MJ-1", lambda: "item-2")
except TransientError:
    print("error propagates, rows:", store.rows)
print(resolve(store, "MJ-1", lambda: "item-2"))
```

**Follow-up they will ask:** "What if two external ids should be the same internal record, say after a customer merges duplicates?"

**A:** My schema does not support that today. `UNIQUE (system, internal_id)` stops two external ids in one system from pointing at one internal record, which protects the reverse lookup, so a merge would be a deliberate migration: pick the survivor, repoint the link, tombstone the loser, and replay the loser's history through the version gate. I would raise it as a discovery question with the customer before promising anything, because the answer depends on whether their merge emits an event.

---

## Phase 4 — Deciding what wins (field ownership, version tie-break, last-write-wins, echo-loop prevention)

### 🟢 Beginner

**Q:** Two systems both edited the same record. Who wins?

**A:** The safest answer is that most of the time it should not be a contest, because each field has exactly one owner and only the owner's edits count. In my build the external system owns title and status and my side owns notes, so a title change from the vendor is applied and a notes change from the vendor is not. For the rare field that both sides can edit I would need an explicit rule, and I would never pick a winner by comparing wall-clock times from two machines, because clocks drift and silently lose edits. I report the disagreement as a `conflict` instead of hiding it.

### 🟡 Intermediate

**Q:** How does your ownership merge work, and what outcomes can an incoming change produce?

**A:** `Ownership` is a map from field to owner, and any field not listed defaults to internal-owned, so a forgotten config entry can never let the vendor overwrite local data. `Merge` takes the external-owned fields from the incoming event and keeps the internal-owned fields from the current row, and it returns the list of internal-owned fields where the incoming value disagreed. If that list is non-empty the outcome is `conflict`, but the external-owned fields are still applied and the internal value is kept, so nothing is lost silently. The other outcomes are `applied` for a newer version merged in, `ignored_stale` for a version that is not newer, and `echo` for a webhook that is just my own earlier push coming back. The loader uses the same map in reverse, `PatchFor`, so it only ever writes the fields I own.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/ownership.go:23-25`

```go
func DefaultOwnership() Ownership {
	return Ownership{FieldTitle: OwnerExternal, FieldStatus: OwnerExternal, FieldNotes: OwnerInternal}
}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/ownership.go:31-50`

```go
// Merge takes external-owned fields from incoming and keeps internal-owned
// fields from current. rejected lists internal-owned fields where incoming
// disagreed: the external system edited a field it does not own.
func (o Ownership) Merge(current, incoming Content) (merged Content, rejected []Field) {
	pick := func(f Field, cur, in string) string {
		if o.externalOwns(f) {
			return in
		}
		if in != cur {
			rejected = append(rejected, f)
		}
		return cur
	}
	merged = Content{
		Title:  pick(FieldTitle, current.Title, incoming.Title),
		Status: pick(FieldStatus, current.Status, incoming.Status),
		Notes:  pick(FieldNotes, current.Notes, incoming.Notes),
	}
	return merged, rejected
}
```

**How to talk about it:** I say "per-field single writer first, version second, human last", and I point out that the conflict test asserts all three values at once: outcome `conflict`, status `Done`, notes `mine`.

### 🔴 Senior

**Q:** Why not last-write-wins on timestamps, how does the version gate work, and which of your echo-loop guards actually matters?

**A:** Last-write-wins on a client clock loses edits whenever clocks skew; the illustrative snippet below shows a 500 ms skew picking the older edit. My offline mobile sync in `internal/sync` does use last-write-wins on `updated_at`, which is acceptable there because it is devices syncing against my own server and a tie is classified, but for two servers I order events by the external system's own monotonic `version`. The gate is one SQL statement, `UPDATE external_id_map SET last_version = $v WHERE last_version < $v`, so zero rows back means stale or duplicate, and the same statement row-locks the link until the transaction ends. Equal versions are stale, so a replay is a no-op; that is stricter than my `mergeLatest` drill, where `>=` lets the later arrival win a tie, and I say which rule I chose out loud. For echo prevention I have three independent layers: single-writer fields, an origin filter in the loader that skips events stamped `system:<sys>`, and an echo memory holding the version and content hash of the PATCH response. In the default configuration any one of the three ends the loop, so a test that only asserts "the loop terminates" would still pass with the echo memory removed. What the memory uniquely buys is an accurate `echo` label and no false `conflict` when the echo of an older push arrives after a newer local edit; that one test fails without it. There is also a known race: if the webhook is processed before the loader records its push, it is not labelled `echo`, the merge is a no-op and the loop still ends. I measured nothing about conflict rates, because the only vendor is my mock; what I can claim is 15 integration tests on real Postgres plus a by-hand mutation check where removing each safeguard made at least one test fail.

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

**Source:** `GolangExercise/offline-sync-app/internal/twoway/apply.go:60-76`

```go
	if src == SourceWebhook {
		echo, err := a.isEcho(ctx, q, internalID, issue)
		if err != nil {
			return "", err
		}
		if echo {
			return OutcomeEcho, nil
		}
	}

	_, err = q.AdvanceLinkVersion(ctx, db.AdvanceLinkVersionParams{System: a.system, ExternalID: issue.ID, Version: issue.Version})
	if errors.Is(err, pgx.ErrNoRows) {
		return OutcomeIgnoredStale, nil
	}
	if err != nil {
		return "", fmt.Errorf("advance version of %s/%s: %w", a.system, issue.ID, err)
	}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/apply.go:116-116`

```go
	return pushed.ExternalVersion == issue.Version && pushed.ContentHash == ContentOf(issue).Hash(), nil
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:279-292`

```go
	e.items.EditNotes(context.Background(), id, "A", "user-1")
	e.runLoader()
	e.items.EditNotes(context.Background(), id, "B", "user-1")
	e.deliverAndProcess(mockjira.FlushInOrder)

	if got := e.inboxOutcomes()["dlv-2"]; got != "echo" {
		t.Errorf("echo of push A after local edit B = %q, want echo, not a false conflict", got)
	}
	e.runLoader()
	e.deliverAndProcess(mockjira.FlushInOrder)

	if got := e.inboxOutcomes()["dlv-3"]; got != "echo" {
		t.Errorf("echo of push B = %q, want echo", got)
	}
```

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:10-16`

```sql
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    updated_at = EXCLUDED.updated_at
WHERE EXCLUDED.updated_at > disaster_locations.updated_at
RETURNING *;
```

Why a skewed client clock makes last-write-wins lose an edit while the server version does not:

**Illustrative (not from the repo):**

```python
edits = [
    {"value": "Done", "client_ms": 1_000_500, "version": 1},
    {"value": "Reopened", "client_ms": 1_000_000, "version": 2},
]
print(max(edits, key=lambda e: e["client_ms"])["value"])
print(max(edits, key=lambda e: e["version"])["value"])
```

**Follow-up they will ask:** "DevRev has its own loop prevention. How does it relate to yours, and what would you do for a field both sides can edit?"

**A:** From README section 1, after a write the AirSync SDK records the mapper's `external_versions` as `{ modified_date, recipe_version: 0 }`, and the connector has to return the external system's real `modifiedDate` from the write and keep the same `modified_date` during extraction, so the next import recognises DevRev's own change by version matching. That is my echo memory in different clothes: remember the version I wrote, drop the change that comes back carrying it, and never fabricate the timestamp because that silently breaks the match. For a field both sides can edit I would stop reporting and start merging three ways, using the last-synced snapshot as the base; the drill's three-row echo table (drop as echo, apply, conflict) is the cheap version, and its own pitfalls note that a content hash alone mistakes an old echo for a remote edit, which is why my build stores the version too. To compute which fields changed I would reuse the drill's field-level diff.

---

## Phase 5 — Loading changes back (idempotency key, 429 Retry-After, backoff with jitter)

### 🟢 Beginner

**Q:** What does "loading changes back" mean, and what is an idempotency key?

**A:** After the vendor's changes are in my system, my users also edit things, and those edits have to be written back to the vendor; DevRev calls that data loading, and I call the code the loader. The risk is a network failure after the vendor already applied my write: if I just retry, the change could be applied twice. An idempotency key is a unique id I send with the write, so the server recognises a repeat and replays its first answer instead of applying it again. In my build the key is the id of the domain event that caused the push, so a retry of the same event always carries the same key.

### 🟡 Intermediate

**Q:** Walk me through how an internal edit reaches the external system in your implementation.

**A:** An internal edit writes the row and a domain event in one transaction, which is the outbox idea, with the user as the actor. The loader consumes `work_item.updated` events and first drops any event whose actor is `system:<sys>`, because that change came from the vendor and must not be reflected back. It looks up the external id through the reverse mapping, builds a PATCH containing only the internal-owned fields, and sends it with the event id as the `Idempotency-Key`. On success it stores the version and a hash of the response, which is the echo memory the webhook path later consults. A failure the loader cannot fix by waiting, such as an exhausted retry or a permanent 4xx, is dead-lettered with its payload, while anything else, like a cancelled context, is returned so the event stays unprocessed for the next tick.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/loader.go:37-40`

```go
func (l *Loader) Handle(ctx context.Context, evt db.DomainEvent) error {
	if evt.ActorSub == OriginActor(l.system) {
		return nil
	}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/loader.go:61-75`

```go
	issue, err := l.pusher.Patch(ctx, link.ExternalID, patch, evt.ID.String())
	if err != nil {
		return l.onPushError(ctx, evt, err)
	}

	if err := l.q.UpsertSyncPushed(ctx, db.UpsertSyncPushedParams{
		System:          l.system,
		InternalID:      evt.AggregateID,
		ExternalVersion: issue.Version,
		ContentHash:     ContentOf(issue).Hash(),
	}); err != nil {
		return fmt.Errorf("remember pushed version of %s: %w", evt.AggregateID, err)
	}
	return nil
}
```

**How to talk about it:** I stress that two different things make the push safe: the idempotency key handles "the write succeeded but I never saw the answer", and the origin filter handles "this change was never mine to push". The mock vendor implements the key by replaying the stored response, shown in the next snippet.

**Source:** `GolangExercise/offline-sync-app/internal/mockjira/handler.go:98-111`

```go
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

### 🔴 Senior

**Q:** The vendor throttles you with 429, returns 5xx, or drops the response. What exactly happens, how long can it take, and where does it leak?

**A:** For 429 the client waits exactly the server's `Retry-After`, and for 5xx or network errors it waits a full-jitter delay, which is a uniform random draw from zero up to the lesser of the cap and the base times two to the attempt. Other 4xx responses are permanent and not retried, and after the maximum attempts the loader dead-letters the event with the reason. With the default policy of five attempts, a 200 ms base and a 10 s cap, the jitter ceilings between attempts are 0.2, 0.4, 0.8 and 1.6 seconds, so at most 3.0 seconds of sleeping, and with the client's 10 second request timeout the worst case per push is about 53 seconds; that is arithmetic on the constants, not a measurement, and it excludes any `Retry-After` wait. The leaks are these. `Retry-After` is unbounded, with the context deadline as the only cap, only the delta-seconds form is parsed and an HTTP-date is treated as absent, and a long sleep inside a page can overrun the extraction budget. The client retries any method without checking that an idempotency key was supplied, whereas my TypeScript drill gates retries on an idempotent method or a key, so today only the loader's discipline makes the PATCH safe. Also, the drill treats `Retry-After` as a floor with `max(jittered, hinted)`, while the Go client uses it as the exact wait, and I would say which one I mean. The integration test proves one 2-second wait and one write that landed exactly once, and the boundary is that the mock's idempotency memory never expires, while a real vendor's key retention is unknown to me.

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

**Source:** `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:320-326`

```go
	e.jira.FailNext(1, http.StatusTooManyRequests, 2*time.Second)

	e.runLoader()

	jiraIssue, _ := e.jira.Get(issue.ID)
	if len(e.sleeps) != 1 || e.sleeps[0] != 2*time.Second || jiraIssue.Description != "notes" || jiraIssue.Version != 2 {
		t.Errorf("sleeps = %v, jira = %+v, want one 2s wait then the write landed once", e.sleeps, jiraIssue)
```

The cap I would add for a Lambda-sized budget, with an HTTP-date form, ran in isolation:

**Illustrative (not from the repo):**

```python
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def retry_after_seconds(value: str, now: datetime, max_wait: float) -> float | None:
    if re.fullmatch(r"[0-9]{1,9}", value):
        wait = float(value)
    else:
        try:
            wait = max(0.0, (parsedate_to_datetime(value) - now).total_seconds())
        except (TypeError, ValueError):
            return None
    return wait if wait <= max_wait else None


now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
for header in ("7", "3600", "Tue, 20 Oct 2026 12:00:30 GMT", "foo 3"):
    print(header, "->", retry_after_seconds(header, now, 60))
```

**Follow-up they will ask:** "A vendor answers `Retry-After: 3600` and you are inside a 10-minute budget. What do you do?"

**A:** I do not sleep, because sleeping burns the budget and, on a platform that bills for run time, money. I give up on that item for this run, record it as pending with the delay, and let the next invocation or the queue's redelivery handle it. DevRev's data loading has exactly that shape: for a rate limit the callback returns a `delay` such as `delaySeconds: 30` and the item stays pending, and a callback error is counted as an item failure with no automatic retry (README section 1). I would also tell them that `item.id.devrev` is described in the docs as suitable for a stable idempotency key, which is the same role my event id plays; re-check the exact field names in the current docs before the interview.

---

## Phase 6 — Resumable backfill under a time budget

### 🟢 Beginner

**Q:** What is a backfill, and why does it have to be resumable?

**A:** A backfill is the first big import, where I pull all the existing history from the other system, often millions of records, page by page. It has to be resumable because the process doing it can be killed or restarted at any time, and on a serverless platform it is killed on purpose when it runs past its time limit. If it could not resume, every restart would begin from page one and never finish. So after each page I save a checkpoint with the cursor, and the next run continues from that cursor.

### 🟡 Intermediate

**Q:** Walk me through how your extraction loop stops and resumes.

**A:** At the start of a run I read the stored sync state. If a cursor is stored, a run was in flight, so I reuse its `run_since` and its running maximum of `updatedAt`; if the cursor is empty, I start a new run from the watermark minus an overlap window, or from zero on the very first run. Before each page I check the time left, and I stop cleanly if there is none or if less than the slowest page so far remains, so I never start work I cannot finish. For each page I apply every issue and write the checkpoint inside one transaction, so a crash replays at most one page, and the replay is a no-op because of the version gate. A positive budget always processes at least one page, so a tiny budget cannot livelock. When the last page lands, the watermark moves to the maximum `updatedAt` seen, and the next run starts the overlap earlier.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/extractor.go:72-76`

```go
	for {
		remaining := deadline.Sub(e.clock())
		if remaining <= 0 || remaining < slowest {
			return res, nil
		}
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/extractor.go:91-98`

```go
		err = e.tx.InTx(ctx, func(q db.Querier) error {
			for _, issue := range page.Issues {
				if _, err := e.applier.Apply(ctx, q, SourcePoll, issue); err != nil {
					return err
				}
			}
			return q.UpsertSyncState(ctx, e.checkpoint(state, since, next, runMax))
		})
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/extractor.go:114-125`

```go
func (e *Extractor) checkpoint(prior db.SyncState, since time.Time, next string, runMax pgtype.Timestamptz) db.UpsertSyncStateParams {
	if next == "" {
		return db.UpsertSyncStateParams{System: e.system, Watermark: runMax}
	}
	return db.UpsertSyncStateParams{
		System:     e.system,
		Watermark:  prior.Watermark,
		RunSince:   pgtype.Timestamptz{Time: since, Valid: true},
		NextCursor: next,
		RunMax:     runMax,
	}
}
```

**How to talk about it:** I say the order matters: fetch, apply and checkpoint together, never checkpoint first, because checkpointing first would lose a page on a crash. The unit test uses a fake clock to show the budget rule exactly.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/extractor_test.go:136-144`

```go
func TestRun_StopsBeforeAPageItCannotFinishAndResumesFromTheCheckpoint(t *testing.T) {
	f := newExtractorFixture(t, 100*time.Second, 40*time.Second)
	f.q.EXPECT().GetSyncState(gomock.Any(), testSystem).Return(db.SyncState{}, pgx.ErrNoRows)
	f.q.EXPECT().UpsertSyncState(gomock.Any(), gomock.Any()).Return(nil).Times(2)

	first, err := f.extractor.Run(context.Background())

	if err != nil || first.Done || first.Pages != 2 {
		t.Fatalf("first Run() = %+v, %v, want 2 pages and not done: 100s budget, 40s pages, 20s left < 40s slowest", first, err)
```

### 🔴 Senior

**Q:** The platform kills you at a hard limit and DevRev gives you a soft timeout. How do you design extraction so every invocation makes progress, and where does yours still fall short?

**A:** From README section 1, DevRev's soft timeout `options.timeout` is capped at ten minutes and the hard kill comes at 1.3 times the soft timeout, about 13 minutes; the worker is expected to check `adapter.isTimeout` between pages or batches and return in time for the SDK to save progress, and the hard kill is not a checkpoint to rely on. State resumes at the next unconsumed page, reads and writes must be replay-safe, and the docs advise compact JSON state for cursors and per-type completion. My extractor has the same shape: a budget checked before each page with room reserved for the slowest page, a cursor persisted with the data, and idempotent writes. The failure modes are these. A page that hangs or sleeps is not bounded by the budget check, because the check happens only between pages; the HTTP client has a 10 second timeout, but a `Retry-After` sleep inside a page is unbounded and can overrun the budget. The extractor assumes one runner, so two runners duplicate work and the last checkpoint wins, and the fix is an advisory lock or a single scheduled invocation. Rows that commit late with an older timestamp than the overlap window are missed, and the fix is a periodic full reconcile, which is not built. The watermark uses the vendor's `updatedAt`, so I am trusting the vendor's clock for the poll window, while ordering inside the application still uses the version. For numbers: in the integration test, 7 issues with a page size of 3 crash on page 2, leave exactly 3 links and the checkpoint at page 2's cursor, and after resume produce 7 links, 7 events and zero duplicates; the unit test with a 100 s budget and 40 s pages proves the stop rule using a fake clock. I have not measured throughput or page latency against a real vendor, so I make no claim about records per second. The default `EXTRACT_BUDGET` in my config is ten minutes, which happens to match the DevRev cap, but for DevRev I would set my own limit below the soft timeout and use `isTimeout` rather than rely on the hard kill.

**Follow-up they will ask:** "Millions of tickets across many tenants. How does this scale, and is it exactly-once?"

**A:** It is at-least-once delivery plus an idempotent, version-guarded write, which gives effectively-once, not exactly-once end to end. To scale I would shard by tenant or key range, give each shard its own checkpoint, fan out through a queue, and put one shared rate limiter in front of the vendor so the vendor's limit is respected across shards; ordering across shards is not guaranteed and I would say so. The portable drill shows the same four invariants in TypeScript: budget check before the page, fetch then write then checkpoint, idempotent upsert, and a positive budget always doing one page.

---

## Phase 7 — Deletes, dead letters and reconciliation

### 🟢 Beginner

**Q:** How should a sync handle deletes, and what is a dead letter?

**A:** A delete is just another change that has to be synced, so I record it as a tombstone, meaning I flag the row as deleted instead of removing it. I never infer a delete from a record being absent in a poll, because an incremental poll only returns changes, so a missing row proves nothing. A dead letter is a message that keeps failing; after a fixed number of attempts I move it to a separate table with the raw payload and the reason, so it stops blocking everything behind it. A person can then look at it and decide whether to fix and replay it.

### 🟡 Intermediate

**Q:** How do your tombstones work, and what happens when a delete arrives before its create?

**A:** A delete is applied like any other event, at a higher version, and the upsert sets `deleted_at` instead of deleting the row; once set, the `COALESCE` keeps the first deletion time. The vendor's list endpoint includes tombstones, so an incremental poll can see deletes too. Because the version gate orders events, a delete at version 2 that arrives before its create at version 1 is applied, and the late create is `ignored_stale`, so the record is not resurrected. One test proves that a poll returning no rows deletes nothing, and the row still exists with its title after a real delete event. What I did not build is the outbound direction: the loader only subscribes to `work_item.updated`, so an internal delete is never pushed to the vendor.

**Source:** `GolangExercise/offline-sync-app/sqlc/queries.sql:163-168`

```sql
ON CONFLICT (id) DO UPDATE SET
    title      = EXCLUDED.title,
    status     = EXCLUDED.status,
    notes      = EXCLUDED.notes,
    deleted_at = CASE WHEN sqlc.arg(deleted)::bool THEN COALESCE(work_items.deleted_at, now()) END,
    updated_at = now()
```

**Source:** `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:482-490`

```go
	e.deliverAndProcess(mockjira.FlushReversed)

	outcomes := e.inboxOutcomes()
	if outcomes["dlv-2"] != "applied" || outcomes["dlv-1"] != "ignored_stale" {
		t.Errorf("outcomes = %v, want the delete applied and the late create ignored_stale", outcomes)
	}
	if !e.workItem(issue.ID).DeletedAt.Valid {
		t.Error("work item is not tombstoned: the late create resurrected it")
	}
```

**How to talk about it:** I say the tombstone needs a version just like a create, because a delete without a version can be undone by any stale create that arrives later. The same point is in the merge drill's pitfalls.

### 🔴 Senior

**Q:** Something keeps failing in production. What is your dead-letter policy, how do you replay, how do you know the two systems have drifted, and what is missing?

**A:** In my implementation an inbox row is attempt-counted and moved to `sync_dead_letters` at the maximum with its raw bytes, a reason and the attempt count, and the loader dead-letters on exhausted retries or a permanent 4xx. The payload is stored as bytes because a poison body may not be valid JSON, and the integration test checks that the raw `not json` body and exactly three attempts are recorded and that attempts stop growing afterwards, which is the proof there is no infinite retry. For drift, today I have queries I can run, for example outcome counts, backlog count and oldest unprocessed row, and the dead-letter list. The overlap window on the poll is a partial safety net, but late commits older than the overlap are missed, so real drift detection needs a periodic full reconcile that compares ids and versions on both sides; that is not built, and the snippet below is a sketch of its core. Also missing, and I say so unprompted: no dead-letter replay tooling, no retention job for the inbox, no metrics, tracing or alerting on dead-letter growth, and no secret rotation. A replay is safe in principle because applying is version-gated and the loader's PATCH carries its event id as the idempotency key, but the mock remembers keys forever and I do not know how long a real vendor does. I have no measurement of dead-letter rates, because the only traffic is test traffic.

**Source:** `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:353-358`

```go
	if source != "inbox" || attempts != 3 || reason == "" || string(body) != "not json" {
		t.Errorf("dead letter = %s/%d/%q/%q, want inbox, exactly 3 attempts, a reason and the raw body", source, attempts, reason, body)
	}
	if e.count("SELECT attempts FROM webhook_inbox WHERE system = $1", e.system) != 3 {
		t.Error("attempts kept growing after the dead letter: that is infinite retry")
	}
```

The queries I can run today, taken from the doc:

**Source:** `GolangExercise/offline-sync-app/docs/two-way-sync.md:149-152`

```sql
SELECT outcome, count(*) FROM webhook_inbox WHERE system = 'mockjira' GROUP BY outcome;
SELECT count(*), min(received_at) FROM webhook_inbox WHERE processed_at IS NULL AND dead_at IS NULL;   -- backlog and lag
SELECT source, attempts, reason, created_at FROM sync_dead_letters ORDER BY created_at DESC;
SELECT * FROM sync_state;                                                                              -- checkpoint, in-flight cursor
```

A replay sketch that moves an inbox dead letter back to pending (tested against temp tables in a rolled-back transaction, not built into the repo):

**Illustrative (not from the repo):**

```sql
WITH revived AS (
  UPDATE webhook_inbox i SET attempts = 0, last_error = '', dead_at = NULL
  FROM sync_dead_letters d
  WHERE d.source = 'inbox' AND d.system = i.system AND d.ref_id = i.delivery_id AND d.id = $1
  RETURNING d.id
)
DELETE FROM sync_dead_letters WHERE id IN (SELECT id FROM revived);
```

And the core of a reconciliation pass over ids and versions, with fake data:

**Illustrative (not from the repo):**

```python
def reconcile(external: dict[str, int], internal: dict[str, int]) -> dict[str, list[str]]:
    both = external.keys() & internal.keys()
    return {
        "missing_internally": sorted(external.keys() - internal.keys()),
        "behind": sorted(k for k in both if internal[k] < external[k]),
        "orphaned_internally": sorted(internal.keys() - external.keys()),
    }


print(reconcile({"MJ-1": 3, "MJ-2": 1, "MJ-4": 2}, {"MJ-1": 2, "MJ-2": 1, "MJ-3": 5}))
```

**Follow-up they will ask:** "A vendor outage dead-lettered a thousand good events. Is it safe to replay them all?"

**A:** It is safe for correctness because the version gate makes a replay of anything older than what I already applied a no-op, and an event that is still the newest applies exactly once. It is not automatically safe for load, so I would replay in small batches with the same backoff rules, and I would first confirm the vendor is healthy. I would also separate the dead letters into transient causes, which are replayable, and poison bodies, which need a code or data fix, which is why recording the reason per row matters.

---

## Phase 8 — Third-party integration lessons and the DevRev AirSync mapping

### 🟢 Beginner

**Q:** Tell me about an integration you built against a third-party system. **[P]**

**A:** At Couchbase I owned the invoices integration end to end, where NetSuite was the source of truth and it was reachable only through Workato recipes, covering the Go client, the domain service, the API endpoint and the UI. The contract I was handed was a hypothesis, so I tested it against the live recipe first and found it did not match what was documented. I sized our timeout to the upstream's own, mapped the upstream's "not generated yet" failure to a clear customer message instead of a scary server error, and shipped it dark behind a feature flag with end-to-end tests. I want to be precise that this was a request and response integration, not a webhook or two-way sync, and I do not quote adoption numbers because I do not have verified ones.

### 🟡 Intermediate

**Q:** How does what you built map to DevRev's AirSync concepts?

**A:** The mapping is close, and I say it in DevRev's words. My extraction loop with its budget check and cursor state corresponds to a worker that checks `adapter.isTimeout` between pages and resumes at the next unconsumed page. My `external_id_map` is the identity mapper idea, where a missing mapping means create and an existing one means update. My echo memory is their loop prevention by version matching on `external_versions`. My dead-letter table is roughly their per-item failure report, and my 429 `Retry-After` handling is roughly their `delay` outcome. I would also say the differences: their SDK owns the state and the mappers, so in a real engagement I would write connector code against it, not reuse my Postgres tables, and my build is the evidence that I understand the problems the SDK solves. The wiring below is the local single-process form of my side of that picture, where the inbox worker, extraction and loader run as ticker loops.

| AirSync concept (README section 1) | In my build | Honest gap |
|---|---|---|
| Connector, extraction | `twoway.Extractor`, cursor plus `updated_since` | Mock vendor, no real throughput measured |
| Time limit and resume | Budget check before each page, `sync_state` checkpoint | No `isTimeout` equivalent from a platform |
| Identity mappers | `external_id_map`, `ResolveInternalID` | No `entity_type` yet |
| Loop prevention | Echo memory (version and hash), origin filter, ownership | Overlaps two other guards |
| Data loading | `twoway.Loader`, event id as idempotency key | No outbound deletes or creates |
| Rate limits | 429 with `Retry-After` honoured | Unbounded wait, seconds form only |
| Item failure report | `sync_dead_letters` | No replay tooling or alerting |

**Source:** `GolangExercise/offline-sync-app/cmd/webhook-receiver/main.go:51-58`

```go
	go loop(ctx, "inbox-worker", 2*time.Second, worker.RunOnce)
	go loop(ctx, "extractor", time.Minute, func(ctx context.Context) (int, error) {
		res, err := extractor.Run(ctx)
		return res.Issues, err
	})
	go loop(ctx, "loader", 5*time.Second, func(ctx context.Context) (int, error) {
		return consume.RunOnce(ctx, q, loader.ConsumerName(), loader.EventTypes(), loader.Handle)
	})
```

**How to talk about it:** I say "my names are mine, not DevRev's" so that nobody hears me claim I used their SDK. I use the words extraction, data loading, identity mappers and loop prevention for DevRev, and I keep "extractor" and "loader" for my own package names.

### 🔴 Senior

**Q:** You have only run this against a mock. What would break first against a real vendor, what did the Workato work teach you about that, and what would you do in the first week at a customer?

**A:** The mock is not Jira: its header names, payload shape and pagination are invented, so the first things I would verify are the real signature scheme and header names, the real pagination and `updated_since` semantics, the vendor's rate-limit headers (including whether `Retry-After` comes as seconds or as a date), token refresh and auth, and the ordering and retry guarantees of its webhooks. The Workato work taught me four habits that transfer. First, test the contract against the real system before building on it, because the real contract differed from the documented one and I rebuilt the client. Second, size timeouts to the upstream's own, which I did by setting ours to 35 seconds against Workato's own 30 second request timeout; I took those numbers from my STAR notes and did not re-measure them for this module. Third, turn an upstream status into a typed error with a customer-readable message, as with the 502 and 404 that meant "not generated yet". Fourth, do not trust ids that arrive from outside: that recipe authorizes on invoice id alone, so the service checked ownership first, and my webhook receiver likewise authenticates before it stores anything. In the first week at a customer I would ask which objects and fields matter, which side owns each field, how deletes and merges are signalled, what the vendor's rate limits and webhook guarantees are, and what freshness they actually need, and I would ship the poll path first because it is the correctness net. I would also tell them what I do not know yet, because that is cheaper than learning it in production. The code for the Workato integration is proprietary monorepo code, so I describe the lessons only and cite the location: `/Users/aashishkumar/Documents/GitHub/fourth/couchbase-cloud.worktrees/AV-145302_invoices_split/internal/billing/activations/integrations/`.

**Follow-up they will ask:** "What did you not build, and what would you do first with another week?"

**A:** The honest list from my own docs is no secret rotation, no extraction lock so two runners can collide, no dead-letter replay tooling, no metrics or tracing, and a Lambda that was never applied to AWS and has nothing draining its inbox. With a week I would first make the inbox worker queue-triggered and deploy the receiver and worker together, then add a bound on `Retry-After` and an advisory lock for extraction, and then metrics on inbox lag and dead-letter growth, because those three decide whether I can operate it. Only after that would I touch a real vendor, and I would start with its read path.

---

## Code reference index

| path:lines | what it shows |
|---|---|
| `GolangExercise/offline-sync-app/internal/webhook/verify.go:44-47` | Verify: prefix check and the rule that a delivery id may not contain a dot |
| `GolangExercise/offline-sync-app/internal/webhook/verify.go:58-70` | Verify: MAC over ts.id.body, hmac.Equal on decoded bytes, then the window |
| `AI/interviews/devrev-fde/drills/ts/src/webhook.ts:43-63` | Portable TS drill: constant-time compare, window before MAC, typed failure reasons |
| `GolangExercise/offline-sync-app/internal/webhook/handler_test.go:103-120` | Test: id swapped after signing is 401 and the real delivery still lands |
| `GolangExercise/offline-sync-app/internal/webhook/handler.go:58-62` | Handler: MaxBytesReader, raw read, verify before any DB write |
| `GolangExercise/offline-sync-app/internal/webhook/handler.go:69-79` | Handler: delivery id check, inbox insert, duplicate vs accepted |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:201-205` | InsertWebhookInbox: 1 row = first delivery, 0 rows = duplicate |
| `GolangExercise/offline-sync-app/internal/webhook/worker.go:71-90` | processOne: claim, process, mark processed, commit in one tx |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:213-216` | ClaimInboxRow: FOR UPDATE SKIP LOCKED |
| `GolangExercise/offline-sync-app/internal/webhook/worker.go:100-119` | recordFailure: count attempt, dead-letter at the cap |
| `GolangExercise/offline-sync-app/internal/twoway/apply.go:141-150` | ResolveInternalID: insert-then-select, returns the stored id |
| `GolangExercise/offline-sync-app/migrations/000003_two_way_sync.up.sql:13-20` | external_id_map: PK (system, external_id), UNIQUE (system, internal_id), last_version |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:498-527` | Test: 8 concurrent first sights produce one link, one item, one winner |
| `GolangExercise/offline-sync-app/internal/twoway/ownership.go:23-25` | Ownership type and DefaultOwnership: title/status external, notes internal |
| `GolangExercise/offline-sync-app/internal/twoway/ownership.go:31-50` | Merge: pick per field, collect rejected internal-owned fields |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:299-312` | Test: conflict keeps internal notes, applies external status |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:146-152` | AdvanceLinkVersion: atomic version gate, 0 rows = stale |
| `GolangExercise/offline-sync-app/internal/twoway/apply.go:60-76` | Apply: webhook-only echo check, then the version gate |
| `GolangExercise/offline-sync-app/internal/twoway/apply.go:116-116` | isEcho: exact version AND content hash of the stored response |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:279-292` | Test: echo of an older push after a newer local edit is echo, not conflict |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:10-16` | UpsertLocation: LWW on updated_at (offline mobile sync, not two-way) |
| `AI/interviews/devrev-fde/drills/ts/src/echoGuard.ts:16-32` | Drill: ledger of last-pushed fingerprint and the apply/echo/conflict decision |
| `AI/interviews/devrev-fde/drills/ts/src/mergeRecords.ts:1-13` | Drill: latest version wins, >= means a tie goes to the later record |
| `AI/interviews/devrev-fde/drills/ts/src/jsonDiff.ts:16-39` | Drill: field-level diff producing add/remove/replace changes |
| `GolangExercise/offline-sync-app/internal/twoway/workitems.go:27-43` | EditNotes: edit plus outbox event in one tx, actor = the user |
| `GolangExercise/offline-sync-app/internal/twoway/loader.go:37-40` | Handle: origin filter, skip events the vendor caused |
| `GolangExercise/offline-sync-app/internal/twoway/loader.go:61-75` | Handle: PatchFor, Patch with event id as key, remember pushed version |
| `GolangExercise/offline-sync-app/internal/mockjira/handler.go:98-111` | Mock: repeated Idempotency-Key replays the first response, no second version bump |
| `GolangExercise/offline-sync-app/internal/twoway/client.go:108-127` | do: retry loop, no sleep after the last attempt |
| `GolangExercise/offline-sync-app/internal/twoway/client.go:140-153` | delay: honour Retry-After, otherwise full jitter with cap |
| `GolangExercise/offline-sync-app/internal/twoway/client.go:186-194` | parseRetryAfter: delta-seconds only, HTTP-date treated as absent |
| `GolangExercise/offline-sync-app/internal/twoway/client_test.go:52-72` | Test: 5xx backoff is a draw up to a doubling, capped ceiling |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:320-326` | Test: 429 Retry-After 2s then the write lands once, no dead letter |
| `GolangExercise/offline-sync-app/internal/twoway/loader.go:80-91` | onPushError: dead-letter exhausted/permanent, return the rest |
| `AI/interviews/devrev-fde/drills/ts/src/retry.ts:44-60` | Drill: idempotency gate, retryable class, full jitter, Retry-After as a floor |
| `GolangExercise/offline-sync-app/internal/twoway/extractor.go:72-76` | Run: budget check before each page, resume from stored cursor |
| `GolangExercise/offline-sync-app/internal/twoway/extractor.go:91-98` | Run: page + checkpoint in one tx, Done when cursor empty, slowest page |
| `GolangExercise/offline-sync-app/internal/twoway/extractor.go:114-125` | checkpoint: in-flight state vs closing the run with a watermark |
| `GolangExercise/offline-sync-app/internal/twoway/extractor_test.go:136-144` | Test: 100s budget, 40s pages, stops after 2 pages because 20s left is under 40s |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:380-398` | Test: crash on page 2 leaves page 1 applied and the checkpoint at page 2's cursor |
| `GolangExercise/offline-sync-app/migrations/000003_two_way_sync.up.sql:32-41` | sync_state: watermark, run_since, next_cursor, run_max |
| `GolangExercise/offline-sync-app/internal/mockjira/mockjira.go:172-201` | Mock vendor List: keyset pagination on (UpdatedAt, ID), tombstones included |
| `AI/interviews/devrev-fde/drills/ts/src/extractor.ts:28-51` | Drill: budget check, fetch/upsert/checkpoint order, slowest-page reserve |
| `GolangExercise/offline-sync-app/sqlc/queries.sql:163-168` | UpsertWorkItem: deleted flag sets deleted_at, never DELETE |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:449-475` | Test: a poll with no rows deletes nothing; delete event tombstones, row remains |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:482-490` | Test: delete before create still wins by version |
| `GolangExercise/offline-sync-app/internal/twoway/integration_test.go:353-358` | Test: poison body dead-lettered after exactly 3 attempts, attempts stop growing |
| `GolangExercise/offline-sync-app/migrations/000003_two_way_sync.up.sql:60-69` | sync_dead_letters: source, ref_id, raw payload, reason, attempts |
| `GolangExercise/offline-sync-app/internal/twoway/loader.go:93-105` | Loader deadLetter: payload, reason and attempts recorded |
| `GolangExercise/offline-sync-app/docs/two-way-sync.md:149-152` | Observability queries: outcomes, backlog and lag, dead letters, checkpoint |
| `GolangExercise/offline-sync-app/cmd/webhook-receiver/main.go:51-58` | Wiring: inbox worker, extractor and loader as ticker loops in one process |

## Self-check

1. **Why is the delivery id inside the MAC?** Because the inbox dedupes on it, so an unsigned id lets a captured body be posted under the id of a real upcoming delivery, and the real one would then be dropped as a `202 duplicate`.
2. **Why answer 202 for a duplicate and 500 for a database failure?** The duplicate is already stored so the sender must stop retrying, while a database failure means nothing is stored so the sender must retry.
3. **What does `WHERE last_version < incoming` buy you that a timestamp compare does not?** It orders events by the external system's monotonic version in one atomic statement, so client clocks never decide a conflict and a replay is a no-op.
4. **Which of the three echo-loop guards is the only one a test needs echo memory for?** The case where the echo of an older push arrives after a newer local edit, which would otherwise be reported as a false `conflict`.
5. **What stops a crash mid-backfill from losing or duplicating a page?** The page and its checkpoint commit in one transaction and replay goes through the version gate, so at most one page is re-read and re-applying it changes nothing.

## What not to claim

- Do not say any of this ran against a real vendor or in production: it runs against my own mock Jira, and the Lambda was never applied to an AWS account.
- Do not say a deployed Lambda would process events: only the receiver has a Lambda, and nothing drains `webhook_inbox` there.
- Do not say the echo memory is the thing that ends loops: it overlaps single-writer fields and the origin filter, and only the older-push-after-newer-local-edit test needs it.
- Do not claim secret rotation, an extraction lock, dead-letter replay tooling, metrics or tracing: none is built.
- Do not claim exactly-once: it is at-least-once plus idempotent, version-gated writes.
- Do not say the drill signs the delivery id or uses `Retry-After` the way the Go client does: the TypeScript and Python drills sign `timestamp.body`, and they treat `Retry-After` as a floor.
- Do not use "extractor" or "loader" as DevRev terms; say extraction and data loading, and re-check the DevRev AirSync pages (timeouts, mappers, loop prevention, data loading) the week of the interview because docs change.
- Do not quote throughput or conflict rates: the only measurements here are a 0.93 microsecond and 0.44 millisecond verify micro-benchmark on an M2 Pro, test results, and arithmetic on constants.
- Do not quote the Workato code, tokens or customer data; describe the lessons and cite the path only, and say "I built" only for code I wrote.
- Do not state from memory that Stripe, Slack or the Standard Webhooks spec sign a particular way without checking: my docs mark those as from memory.
