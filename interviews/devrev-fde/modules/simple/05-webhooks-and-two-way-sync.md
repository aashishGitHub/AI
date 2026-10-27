# Module 05 in plain English: Webhooks and two-way sync

> **Read this first**
> - **What it is for:** learning how to receive webhooks safely and keep two systems in sync, in simple words.
> - **Who it is for:** a beginner. No repo knowledge needed.
> - **Full module:** [05-webhooks-and-two-way-sync.md](../05-webhooks-and-two-way-sync.md). Read it after this file.

**Honesty lanes used in this file.** [P] = shipped at Couchbase. [L] = my own build. [K] = knowledge only.

- Everything about webhooks and two-way sync is **[L]**. I built it and ran it against a **mock** Jira that I wrote. It never ran against a real vendor.
- The one **[P]** item is the Workato/NetSuite invoices integration in Phase 8. It was request and response. It was not a webhook and not a two-way sync.
- DevRev facts come from the repo README section 1. They were checked on 2026-10-19. Docs change, so re-check them the week of the interview.
- The code lives in a sibling repo, `GolangExercise/offline-sync-app`. See [that folder](../../../../../GolangExercise/offline-sync-app/) and the portable drills in [drills](../../drills/).

**Big picture.** DevRev's core product is AirSync (it copies data between a customer's tools and DevRev). This module is where that meets code I wrote.

```
vendor -> webhook -> verify -> inbox (202) -> worker -> apply -> my DB
my DB edit -> event -> loader -> PATCH -> vendor
poll (backfill) runs underneath as the safety net
```

I use DevRev's words "extraction" and "data loading". "Extractor" and "loader" are only my package names.

---

## Phase 1: Receive and verify a webhook (raw bytes, HMAC, constant-time, timestamp window, signed delivery id)

**Analogy: a post office counter.** A parcel arrives with a wax seal. The clerk checks the seal against a shared stamp. Then the clerk checks the date on the parcel. A broken seal or an old date means the parcel is refused.

### What a webhook is and why we verify it

- A webhook is the other system calling a URL of mine when something changes.
- The alternative is me asking over and over (polling).
- My URL is public, so anyone on the internet can POST to it.
- I need proof that the sender knows a secret we share.
- The sender computes an HMAC-SHA256 (a hash made with the shared secret) over the request.
- I compute the same thing on my side. If both match, the body was not changed and the sender knows the secret.
- I never treat webhooks as complete. They can be dropped, repeated or reordered.
- So a poll runs underneath as the safety net.

### How my verify function works

- The signed text is: timestamp, a dot, the delivery id, a dot, then the raw body bytes.
- The header looks like `sha256=<hex>`.
- I verify the exact bytes I received.
- If I parsed the JSON and re-encoded it, spacing or key order could change. Then the signature would no longer match.
- A test signs a body with odd spacing to prove this.
- I decode the hex and compare bytes with `hmac.Equal`. That is a constant-time compare (it takes the same time whether the first byte or the last byte differs).
- A normal `==` on strings can leak how many leading bytes matched.
- The timestamp is inside the signature.
- I reject anything more than five minutes away, in either direction. That limits replay (re-sending a captured request).
- The window check comes after the signature check.
- I reject a delivery id that contains a dot. The dot is my separator.
- Without that rule, a captured request could shift body bytes into the id and keep a valid signature.
- The TypeScript drill in `drills/ts/src/webhook.ts` is simpler. It signs `timestamp.body`, checks the window first and returns typed reasons.
- It does not sign the delivery id. Say which one you are describing.

### Why the delivery id is signed

- The inbox dedupes on the delivery id.
- If the id were not signed, an attacker could post a captured body under the id of a real delivery that has not arrived yet.
- The real delivery would then be dropped as a duplicate.
- A test pins this. An id swapped after signing gets 401 `bad_signature`, nothing is stored, and the genuine delivery still lands with 202.

### What is still open

- An exact replay inside the five-minute window still verifies. It hits the inbox primary key and becomes a harmless `202 duplicate`.
- There is no secret rotation. There is one secret and no overlap window where two secrets work.
- On the Lambda variant the secret is an environment variable. Anyone with `lambda:GetFunctionConfiguration` can read it.
- Fetching it from Secrets Manager at cold start is stronger. I did not build it.
- Cost: I benchmarked a copy of `verify.go` in a scratch module on an Apple M2 Pro.
- About 0.93 microseconds for a 1 KiB body. About 0.44 milliseconds for a 1 MiB body, which is the default body cap.
- This is an in-memory micro-benchmark. It is not a Lambda or network measurement.
- It only says that verification is not the bottleneck.
- The mock vendor signs with my own scheme, so a self-consistent mistake would pass.
- The guard is a test vector made with `openssl dgst -sha256 -hmac`. Both the verifier and the mock check against it.
- A real vendor's header names and signing recipe will differ.
- From memory, the Standard Webhooks spec signs `id.timestamp.body`. Verify this before an interview.

### Follow-up: rotating the secret without dropping deliveries

- Accept signatures from both the old and the new secret for an overlap period.
- Retire the old one once the vendor confirms it switched.
- Do not return early on the first match. Then timing does not reveal which secret matched.
- Log which secret verified, so you can see when the old one goes quiet.
- This is not built in my repo. It is only a sketch I ran in isolation.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Webhook | The other system calls my URL when something changes. |
| HMAC-SHA256 | A hash made with a shared secret; proves who sent it and that it was not changed. |
| Constant-time compare | A comparison that takes the same time however many bytes match. |
| Replay | Re-sending a request someone captured earlier. |
| Timestamp window | The allowed gap between the signed time and now (five minutes here). |
| Delivery id | A unique id the sender gives each webhook delivery. |
| Secret rotation | Changing the shared secret without breaking live traffic. |

**Say it in one breath:** I check an HMAC over timestamp, delivery id and exact body bytes, in constant time, inside a five-minute window.

---

## Phase 2: Inbox, dedupe and acknowledging fast (202)

**Analogy: a restaurant order slip.** The waiter writes your order, pins it to the rail and says "got it". The kitchen cooks later at its own pace. The waiter does not stand there until the food is ready.

### Why answer 202 fast

- The sender only needs to know I stored its event.
- So I authenticate it, write it down, and answer straight away.
- 202 means "accepted, not processed yet".
- If I did the real work inside the request, the sender's retries would depend on my database health and my slowest handler.
- A bad body would be retried by them forever.
- The stored row is called an inbox.
- A separate worker processes it later.
- The price: the data is eventually consistent (it catches up, not instantly). Be clear about that with customers.

### Dedupe and status codes

- The inbox primary key is the system name plus the delivery id.
- The insert is `ON CONFLICT DO NOTHING`.
- So "have I seen this" and "is the raw event stored" are one atomic statement (all or nothing, in one step). They cannot disagree.
- First delivery: one row inserted, `202 accepted`.
- Repeat: zero rows inserted, `202 duplicate`. The sender must stop retrying, and the first copy is already stored.
- Body over the size cap: `413`.
- Unreadable body: `400`.
- Failed verification: `401`, and nothing is written.
- Missing delivery id: `400`.
- Database failure: `500`, so the sender does retry.
- I authenticate before touching the database. Unauthenticated traffic never costs a row.
- The two deliberate choices: 202 for a duplicate (stop retrying) and 500 for a database failure (please retry).
- The same router is mounted by `cmd/webhook-receiver` and by the Lambda entrypoint. The two runtimes cannot drift.

### How the worker behaves

- The worker takes pending rows in batches of 25.
- For each row it opens one transaction (a group of steps that all succeed or all roll back).
- It claims the row with `FOR UPDATE SKIP LOCKED` (lock this row, and skip rows another worker holds).
- It runs the processor, marks the row processed, and commits.
- A crash means nothing happened. Two workers never take the same row.
- A failing row does not block the batch.
- Its attempt count goes up in a separate transaction.
- At the maximum it is copied to `sync_dead_letters` as raw bytes and marked dead.
- In the integration test, a body that is not JSON is dead-lettered after exactly three attempts. The test configures three.
- The shipped default from `SYNC_MAX_ATTEMPTS` is five.
- A weakness I name myself: inbox retries have no backoff beyond the tick interval.
- A poison body (one that can never succeed) burns the same attempts as a transient database error.
- Drain rate: the local process ticks every two seconds with a batch of 25.
- So the ceiling is about 12.5 deliveries per second per worker.
- That number is derived from the constants. I did not measure it.
- In production I would make the worker queue-triggered, not ticker-driven.
- The Lambda was never applied to AWS.
- Deployed alone, it would fill `webhook_inbox` while nothing drained it. The worker only runs inside `cmd/webhook-receiver`.

### Follow-up: why a Postgres inbox and not a queue in front?

- One `INSERT ... ON CONFLICT DO NOTHING` gives dedupe and a durable raw event in one atomic step.
- The applied change, the domain event and the processed mark can commit in the same transaction as the work.
- A queue such as SQS needs its own dedupe story.
- I am not certain of the exact FIFO dedupe window. Verify it before quoting.
- The cost: I own retention. There is no cleanup job for `webhook_inbox` yet.
- I also own the polling or triggering of the worker.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| 202 Accepted | "I stored it; I have not processed it yet." |
| Inbox | A table where raw incoming events are stored before processing. |
| Atomic | Happens fully or not at all, in one step. |
| Eventually consistent | The data catches up after a delay, not instantly. |
| SKIP LOCKED | A Postgres option: skip rows that another worker has locked. |
| Poison message | A message that can never succeed, however often you retry. |
| Dead letter | A message parked after too many failed attempts. |

**Say it in one breath:** I verify, store the raw event in one atomic insert, answer 202, and let a worker apply it later.

---

## Phase 3: Identity mapping (external id to internal id)

**Analogy: a phone book that links two nicknames.** Your friends call you "Ash". Your family calls you "Aashish". The book says both names are one person, so nobody invites you twice.

### What identity mapping is

- The other system calls a record `MJ-1`. My system calls the same record by a UUID.
- I keep a table that says which is which.
- Without it, I could not tell whether an event is a new record or an update.
- I would create duplicates.
- My table is `external_id_map`, keyed by system name plus external id.
- The first time I see an external id, I mint an internal id and store the pair.
- Every later event for that record finds the same internal id.

### Getting the id safely under a race

- A race is two workers seeing the same new id at the same moment.
- I insert first and select second.
- The insert is `ON CONFLICT DO NOTHING` on the primary key `(system, external_id)`.
- If another transaction inserted the same key, mine waits until that one commits, then does nothing.
- Then I select the row and use the stored id. That is the winner's id, not the one I minted.
- The code comment says this is race-safe under READ COMMITTED (a standard Postgres isolation level).
- An integration test fires eight concurrent first sights of one external id.
- It asserts exactly one link, one work item and one `applied` outcome.
- The link row also carries `last_version`.
- A version belongs to one external system's copy of the record. A second system would get its own link and its own version.
- The reverse index `UNIQUE (system, internal_id)` is what the loader uses to find the external id for a push.
- The table has no `entity_type` and no foreign key to `work_items`. That is on purpose.
- I would add `entity_type` before supporting a second entity.

### What the code must not do on a transient error

- A transient error is a short-lived failure, such as a 503.
- It must not treat "the lookup failed" as "the record does not exist".
- If it did, it would mint a second internal id for a record it already has.
- In my code, any error from the select is returned as an error. The page or delivery is retried.
- Only a successful insert-then-select ever yields an id.
- DevRev's mapper docs say the same for `getByExternalId`.
- It returns null when the mapping is missing. Other failures throw `AirSyncHttpError`.
- A connector must never turn a transient failure into "not found" (README section 1).

### Edges of my design

- No `entity_type` in the key. Two entity types with the same external id would collide.
- `ResolveInternalID` generates a fresh UUID on every call, even if a link exists. That wastes a little work.
- I have not measured it. I expect it to be negligible next to a database round trip.
- The loader skips a work item that has no external link. Creating a record internally and pushing it out is not built.
- The claim stops at one entity type against one mock system.

### Follow-up: two external ids that should be one record (a customer merge)

- My schema does not support that today.
- `UNIQUE (system, internal_id)` stops two external ids in one system pointing at one internal record.
- A merge would be a deliberate migration. Pick the survivor, repoint the link, tombstone the loser, replay the loser's history through the version gate.
- I would raise it as a discovery question first. It depends on whether their merge emits an event.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| External id | The id the other system uses for a record. |
| Internal id | The id my system uses for the same record. |
| Mapper / link table | A table that pairs the two ids. |
| Race | Two actors doing the same thing at the same moment. |
| Transient error | A short-lived failure that may work on retry. |
| Entity type | The kind of record (issue, comment, user, and so on). |

**Say it in one breath:** I insert the id pair first and read it back second, so a race always ends with one winner, and a failed lookup is an error, never "not found".

---

## Phase 4: Deciding what wins (field ownership, version tie-break, last-write-wins, echo-loop prevention)

**Analogy: a shared fridge with labelled shelves.** Each shelf belongs to one housemate. Only the owner changes their shelf. Fights over one shelf are rare, and you write them down instead of guessing.

### Who wins when both sides edit

- Most of the time it should not be a contest.
- Each field has exactly one owner. Only the owner's edits count.
- In my build the external system owns title and status. My side owns notes.
- A title change from the vendor is applied. A notes change from the vendor is not.
- For a field both sides can edit, I would need an explicit rule.
- I would never pick a winner by comparing wall-clock times from two machines. Clocks drift and edits get lost silently.
- I report the disagreement as a `conflict`. I do not hide it.

### How the ownership merge works

- `Ownership` is a map from field to owner.
- Any field not listed defaults to internal-owned. A forgotten config entry can never let the vendor overwrite local data.
- `Merge` takes external-owned fields from the incoming event.
- It keeps internal-owned fields from the current row.
- It returns the internal-owned fields where the incoming value disagreed.
- If that list is not empty, the outcome is `conflict`.
- External-owned fields are still applied, and the internal value is kept. Nothing is lost silently.
- Other outcomes: `applied` (a newer version merged in), `ignored_stale` (the version is not newer), `echo` (a webhook that is my own earlier push coming back).
- The loader uses the same map in reverse, `PatchFor`, so it only writes fields I own.
- My phrase: "per-field single writer first, version second, human last".
- The conflict test asserts all three at once: outcome `conflict`, status `Done`, notes `mine`.

### Why not last-write-wins on timestamps

- Last-write-wins (the latest timestamp wins) on a client clock loses edits when clocks are skewed.
- A 500 ms skew can pick the older edit. The module has a small snippet showing this.
- My offline mobile sync in `internal/sync` does use last-write-wins on `updated_at`.
- That is acceptable there. It is devices syncing against my own server, and a tie is classified.
- For two servers, I order events by the external system's own monotonic `version` (a number that only goes up).

### The version gate

- The gate is one SQL statement: update `last_version` to the new version where `last_version` is lower.
- Zero rows back means the event is stale or a duplicate.
- The same statement row-locks the link until the transaction ends.
- Equal versions count as stale. A replay is a no-op.
- That is stricter than my `mergeLatest` drill, where `>=` lets the later arrival win a tie.
- Say out loud which rule you chose.

### Echo-loop prevention

- An echo loop: I push a change, the vendor sends it back as a webhook, I push it again, and so on.
- I have three independent layers.
- Layer 1: single-writer fields.
- Layer 2: an origin filter in the loader. It skips events stamped `system:<sys>`.
- Layer 3: an echo memory. It holds the version and content hash of the PATCH response.
- In the default setup, any one layer ends the loop.
- So a test that only asserts "the loop terminates" would still pass with the echo memory removed.
- What the echo memory uniquely buys: an accurate `echo` label.
- It also stops a false `conflict` when the echo of an older push arrives after a newer local edit. One test fails without it.
- A known race: if the webhook is processed before the loader records its push, it is not labelled `echo`.
- The merge is then a no-op and the loop still ends.
- I measured nothing about conflict rates, because the only vendor is my mock.
- What I can claim: 15 integration tests on real Postgres.
- Also a by-hand mutation check where removing each safeguard made at least one test fail.

### Follow-up: how DevRev's loop prevention relates to mine

- After a write, the AirSync SDK records the mapper's `external_versions` as `{ modified_date, recipe_version: 0 }` (README section 1).
- The connector must return the external system's real `modifiedDate` from the write.
- It must keep the same `modified_date` during extraction.
- Then the next import recognises DevRev's own change by version matching.
- That is my echo memory in different clothes. Remember the version I wrote, and drop the change that comes back carrying it.
- Never invent the timestamp. That silently breaks the match.
- For a field both sides can edit, I would move from reporting to a three-way merge, using the last-synced snapshot as the base.
- The drill's three-row echo table (drop as echo, apply, conflict) is the cheap version.
- Its pitfalls note says a content hash alone mistakes an old echo for a remote edit. That is why my build stores the version too.
- To find which fields changed, I would reuse the drill's field-level diff.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Field ownership | Each field has one side that is allowed to change it. |
| Last-write-wins (LWW) | The newest timestamp wins. |
| Version gate | Only accept a change if its version is higher than the last one applied. |
| Monotonic | Only ever goes up. |
| Echo | My own change coming back to me from the other system. |
| Conflict | Both sides changed a field only one of them owns. |
| Three-way merge | Compare both sides against a shared earlier snapshot. |

**Say it in one breath:** Each field has one owner, events are ordered by the vendor's version, not by clocks, and three layers stop echo loops.

---

## Phase 5: Loading changes back (idempotency key, 429 Retry-After, backoff with jitter)

**Analogy: sending a registered letter with a tracking number.** If the postman says "lost the receipt", you resend with the same number. The office sees the number and does not deliver a second copy.

### What "loading changes back" means

- My users also edit things.
- Those edits must be written back to the vendor.
- DevRev calls this data loading. I call my code the loader.
- The risk: a network failure after the vendor already applied my write. A plain retry could apply it twice.
- An idempotency key (a unique id sent with a write so the server can spot a repeat) fixes this.
- The server replays its first answer instead of applying again.
- In my build the key is the id of the domain event that caused the push.
- A retry of the same event always carries the same key.

### How an internal edit reaches the vendor

- An internal edit writes the row and a domain event in one transaction. That is the outbox idea (events saved with the data, sent later).
- The actor on the event is the user.
- The loader consumes `work_item.updated` events.
- First it drops any event whose actor is `system:<sys>`. That change came from the vendor and must not be reflected back.
- It finds the external id through the reverse mapping.
- It builds a PATCH with only the internal-owned fields.
- It sends the PATCH with the event id as the `Idempotency-Key`.
- On success it stores the version and a hash of the response. That is the echo memory the webhook path checks later.
- A failure that waiting cannot fix is dead-lettered with its payload. Examples: exhausted retries, or a permanent 4xx.
- Anything else, such as a cancelled context, is returned. The event stays unprocessed for the next tick.
- Two different things make the push safe.
- The idempotency key handles "the write worked but I never saw the answer".
- The origin filter handles "this change was never mine to push".
- The mock vendor implements the key by replaying the stored response.

### Rate limits, retries and timing

- For 429 (too many requests), the client waits exactly the server's `Retry-After` time.
- For 5xx or network errors, it waits a full-jitter delay.
- Full jitter: a uniform random draw from zero up to the smaller of the cap and base times two to the attempt.
- Other 4xx responses are permanent. They are not retried.
- After the maximum attempts, the loader dead-letters the event with the reason.
- Default policy: five attempts, 200 ms base, 10 s cap.
- Jitter ceilings between attempts: 0.2, 0.4, 0.8 and 1.6 seconds. At most 3.0 seconds of sleeping in total.
- With the client's 10 second request timeout, the worst case per push is about 53 seconds.
- That is arithmetic on constants. It is not a measurement. It leaves out any `Retry-After` wait.

### Where it leaks

- `Retry-After` is unbounded. The context deadline is the only cap.
- Only the delta-seconds form is parsed. An HTTP-date form is treated as absent.
- A long sleep inside a page can overrun the extraction budget.
- The client retries any method without checking that an idempotency key was supplied.
- My TypeScript drill gates retries on an idempotent method or a key.
- Today only the loader's discipline makes the PATCH safe.
- The drill treats `Retry-After` as a floor: `max(jittered, hinted)`. The Go client uses it as the exact wait. Say which one you mean.
- The integration test proves one 2-second wait and one write that landed exactly once.
- The mock's idempotency memory never expires. A real vendor's key retention is unknown to me.

### Follow-up: `Retry-After: 3600` inside a 10-minute budget

- Do not sleep. Sleeping burns the budget, and on a platform that bills for run time, money.
- Give up on that item for this run. Record it as pending with the delay.
- Let the next invocation or the queue's redelivery handle it.
- DevRev's data loading has this shape (README section 1).
- For a rate limit, the callback returns a `delay` such as `delaySeconds: 30`, and the item stays pending.
- A callback error counts as an item failure with no automatic retry.
- The docs describe `item.id.devrev` as suitable for a stable idempotency key. That is the same role my event id plays.
- Re-check the exact field names in the current docs before the interview.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Idempotent | Doing it twice gives the same result as doing it once. |
| Idempotency key | A unique id sent with a write so the server can spot a repeat. |
| Outbox | Save the event in the same transaction as the data; send it later. |
| 429 / Retry-After | "Too many requests" plus how long to wait. |
| Backoff | Waiting longer between each retry. |
| Full jitter | A random wait between zero and a growing ceiling. |
| Origin filter | Skip events that this other system caused. |

**Say it in one breath:** I push only fields I own, with an idempotency key, and I back off with jitter or as told on 429.

---

## Phase 6: Resumable backfill under a time budget

**Analogy: moving house with numbered boxes.** You carry boxes in trips. After each trip you tick the box number on a list. If the van is called away, you resume from the next unticked box.

### What a backfill is and why it must resume

- A backfill is the first big import of all existing history, often millions of records, page by page.
- The process can be killed or restarted at any time.
- On serverless it is killed on purpose when it passes its time limit.
- Without resuming, every restart begins at page one and never finishes.
- So after each page I save a checkpoint with the cursor (a bookmark for the next page).
- The next run continues from that cursor.

### How my extraction loop stops and resumes

- At the start I read the stored sync state.
- If a cursor is stored, a run was in flight. I reuse its `run_since` and its running maximum of `updatedAt`.
- If the cursor is empty, I start a new run from the watermark minus an overlap window. On the very first run I start from zero.
- The watermark is "everything up to here is done".
- Before each page I check the time left.
- I stop cleanly if there is none, or if less than the slowest page so far remains. I never start work I cannot finish.
- For each page I apply every issue and write the checkpoint inside one transaction.
- A crash replays at most one page. The replay is a no-op because of the version gate.
- Order matters: fetch, apply and checkpoint together. Never checkpoint first, or a crash loses a page.
- A positive budget always processes at least one page. A tiny budget cannot livelock (spin without progress).
- When the last page lands, the watermark moves to the maximum `updatedAt` seen. The next run starts the overlap earlier.
- The unit test uses a fake clock. With a 100 s budget and 40 s pages, it stops after 2 pages. 20 s left is under the 40 s slowest page.

### Hard kill vs soft timeout, and where mine falls short

- From README section 1: DevRev's soft timeout `options.timeout` is capped at ten minutes.
- The hard kill comes at 1.3 times the soft timeout, about 13 minutes.
- The worker should check `adapter.isTimeout` between pages or batches and return in time for the SDK to save progress.
- Do not rely on the hard kill as a checkpoint.
- State resumes at the next unconsumed page. Reads and writes must be replay-safe.
- The docs advise compact JSON state for cursors and per-type completion.
- My extractor has the same shape: a budget check with room for the slowest page, a cursor stored with the data, idempotent writes.
- Failure mode 1: a page that hangs or sleeps is not bounded by the budget check. The check only runs between pages.
- The HTTP client has a 10 second timeout. But a `Retry-After` sleep inside a page is unbounded.
- Failure mode 2: the extractor assumes one runner. Two runners duplicate work and the last checkpoint wins.
- The fix: an advisory lock, or a single scheduled invocation.
- Failure mode 3: rows that commit late with an older timestamp than the overlap window are missed.
- The fix: a periodic full reconcile. Not built.
- Failure mode 4: the watermark uses the vendor's `updatedAt`. I trust the vendor's clock for the poll window.
- Ordering inside the application still uses the version.

### Numbers I can claim

- Integration test: 7 issues, page size 3, crash on page 2.
- It leaves exactly 3 links and the checkpoint at page 2's cursor.
- After resume: 7 links, 7 events, zero duplicates.
- The unit test proves the stop rule with a fake clock.
- I have not measured throughput or page latency against a real vendor. I make no claim about records per second.
- My default `EXTRACT_BUDGET` is ten minutes. That matches the DevRev cap by chance.
- For DevRev I would set my own limit below the soft timeout and use `isTimeout`.

### Follow-up: millions of tickets across many tenants

- It is at-least-once delivery plus an idempotent, version-guarded write.
- That gives effectively-once. It is not exactly-once end to end.
- To scale: shard by tenant or key range, give each shard its own checkpoint, fan out through a queue.
- Put one shared rate limiter in front of the vendor, so its limit holds across shards.
- Ordering across shards is not guaranteed. Say so.
- The portable drill shows four invariants in TypeScript: budget check before the page, fetch then write then checkpoint, idempotent upsert, and a positive budget always doing one page.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Backfill | The first big import of existing history. |
| Cursor | A bookmark that says where the next page starts. |
| Checkpoint | Saved progress so a restart can resume. |
| Watermark | "Everything before this time is done." |
| Overlap window | Start a little before the watermark so late rows are not missed. |
| Soft / hard timeout | A polite deadline, then a forced kill. |
| Livelock | Running forever without making progress. |

**Say it in one breath:** I fetch a page, apply it and save the checkpoint in one transaction, and I stop before a page I cannot finish, so every run makes progress.

---

## Phase 7: Deletes, dead letters and reconciliation

**Analogy: a "returned to sender" shelf and a stock-take.** Bad parcels go to a labelled shelf so the line keeps moving. Now and then someone counts both warehouses to see if the lists agree.

### Deletes and dead letters

- A delete is just another change that must be synced.
- I record it as a tombstone (a flag that says "deleted", with the row kept).
- I never infer a delete from a record being absent in a poll. An incremental poll only returns changes, so a missing row proves nothing.
- A dead letter is a message that keeps failing.
- After a fixed number of attempts, I move it to a separate table with the raw payload and the reason.
- It stops blocking everything behind it.
- A person can look at it and decide whether to fix and replay it.

### How my tombstones work

- A delete is applied like any other event, at a higher version.
- The upsert sets `deleted_at` instead of deleting the row.
- Once set, `COALESCE` keeps the first deletion time.
- The vendor's list endpoint includes tombstones, so an incremental poll can see deletes.
- A delete at version 2 that arrives before its create at version 1 is applied. The late create is `ignored_stale`. The record is not resurrected.
- One test proves a poll returning no rows deletes nothing.
- The tombstone needs a version, like a create. A delete without a version can be undone by any stale create that arrives later.
- What I did not build: the outbound direction. The loader only subscribes to `work_item.updated`, so an internal delete is never pushed to the vendor.

### Dead-letter policy and drift

- An inbox row is attempt-counted. At the maximum it moves to `sync_dead_letters` with raw bytes, a reason and the attempt count.
- The loader dead-letters on exhausted retries or a permanent 4xx.
- The payload is stored as bytes, because a poison body may not be valid JSON.
- The integration test checks the raw `not json` body and exactly three attempts. It also checks that attempts stop growing. That proves there is no infinite retry.
- Drift means the two systems have quietly become different.
- Today I can run queries: outcome counts, backlog count and oldest unprocessed row, and the dead-letter list.
- The overlap window is a partial safety net. Late commits older than the overlap are missed.
- Real drift detection needs a periodic full reconcile, comparing ids and versions on both sides. Not built. The module has a small sketch of its core.
- Missing, and I say so unprompted: no dead-letter replay tooling, no retention job for the inbox, no metrics, tracing or alerting on dead-letter growth, no secret rotation.
- A replay is safe in principle. Applying is version-gated, and the loader's PATCH carries its event id as the idempotency key.
- But the mock remembers keys forever. I do not know how long a real vendor does.
- I have no measurement of dead-letter rates. The only traffic is test traffic.

### Follow-up: a vendor outage dead-lettered a thousand good events

- Replay is safe for correctness. The version gate makes a replay of anything older than what I already applied a no-op.
- An event that is still the newest applies exactly once.
- It is not automatically safe for load.
- Replay in small batches with the same backoff rules. First confirm the vendor is healthy.
- Separate the dead letters by cause. Transient causes are replayable. Poison bodies need a code or data fix.
- That is why the reason is recorded per row.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Tombstone | A "deleted" flag on a row that is kept, not removed. |
| Dead letter | A message parked after too many failures. |
| Drift | The two systems slowly stop agreeing. |
| Reconciliation | Comparing both sides and fixing the differences. |
| Replay | Running stored events through the pipeline again. |
| Resurrect | A deleted record wrongly coming back to life. |

**Say it in one breath:** Deletes are tombstones with versions, poison messages go to a dead-letter table with their reason, and a periodic reconcile, which I have not built, would catch drift.

---

## Phase 8: Third-party integration lessons and the DevRev AirSync mapping

**Analogy: a translator at a meeting.** You learn the other side's vocabulary and say it in their words. You do not pretend their words are yours.

### The Workato story **[P]**

- At Couchbase I owned the invoices integration end to end.
- NetSuite was the source of truth. It was reachable only through Workato recipes (automation workflows).
- I covered the Go client, the domain service, the API endpoint and the UI.
- The contract I was handed was a hypothesis. I tested it against the live recipe first. It did not match what was documented.
- I sized our timeout to the upstream's own.
- I mapped the upstream's "not generated yet" failure to a clear customer message, not a scary server error.
- I shipped it dark behind a feature flag, with end-to-end tests.
- Be precise: this was request and response. It was not a webhook or a two-way sync.
- I do not quote adoption numbers. I have no verified ones.
- The code is proprietary monorepo code. I describe lessons only.

### Mapping my build to AirSync

- My extraction loop with its budget check and cursor state matches a worker that checks `adapter.isTimeout` between pages.
- My `external_id_map` is the identity mapper idea. Missing mapping means create. Existing mapping means update.
- My echo memory is their loop prevention by version matching on `external_versions`.
- My dead-letter table is roughly their per-item failure report.
- My 429 `Retry-After` handling is roughly their `delay` outcome.
- The differences: their SDK owns the state and the mappers.
- In a real engagement I would write connector code against the SDK. I would not reuse my Postgres tables.
- My build is evidence that I understand the problems the SDK solves.
- Locally the inbox worker, extraction and loader run as ticker loops in one process: two seconds, one minute and five seconds.

| AirSync concept | In my build | Honest gap |
|---|---|---|
| Connector, extraction | `twoway.Extractor`, cursor plus `updated_since` | Mock vendor, no real throughput measured |
| Time limit and resume | Budget check before each page, `sync_state` checkpoint | No `isTimeout` equivalent from a platform |
| Identity mappers | `external_id_map`, `ResolveInternalID` | No `entity_type` yet |
| Loop prevention | Echo memory, origin filter, ownership | Overlaps two other guards |
| Data loading | `twoway.Loader`, event id as idempotency key | No outbound deletes or creates |
| Rate limits | 429 with `Retry-After` honoured | Unbounded wait, seconds form only |
| Item failure report | `sync_dead_letters` | No replay tooling or alerting |

- Say "my names are mine, not DevRev's". Nobody should hear me claim I used their SDK.

### What would break first against a real vendor

- The mock is not Jira. Its header names, payload shape and pagination are invented.
- First I would verify the real signature scheme and header names.
- Then the real pagination and `updated_since` behaviour.
- Then the vendor's rate-limit headers, including whether `Retry-After` is seconds or a date.
- Then token refresh and auth.
- Then the ordering and retry guarantees of its webhooks.

### Four habits from the Workato work

- Test the contract against the real system before building on it. The real one differed, and I rebuilt the client.
- Size timeouts to the upstream's own. I set ours to 35 seconds against Workato's 30 second request timeout.
- I took those two numbers from my STAR notes. I did not re-measure them for this module.
- Turn an upstream status into a typed error with a customer-readable message. The 502 and 404 meant "not generated yet".
- Do not trust ids that arrive from outside. That recipe authorizes on invoice id alone, so the service checked ownership first.
- My webhook receiver likewise authenticates before it stores anything.

### First week at a customer

- Ask which objects and fields matter.
- Ask which side owns each field.
- Ask how deletes and merges are signalled.
- Ask about the vendor's rate limits and webhook guarantees.
- Ask what freshness they actually need.
- Ship the poll path first. It is the correctness net.
- Say what I do not know yet. That is cheaper than learning it in production.

### Follow-up: what I did not build, and what I would do first with another week

- No secret rotation.
- No extraction lock, so two runners can collide.
- No dead-letter replay tooling.
- No metrics or tracing.
- A Lambda that was never applied to AWS, with nothing draining its inbox.
- With a week: first make the inbox worker queue-triggered and deploy the receiver and worker together.
- Then bound `Retry-After` and add an advisory lock for extraction.
- Then add metrics on inbox lag and dead-letter growth. Those three decide whether I can operate it.
- Only after that would I touch a real vendor. I would start with its read path.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| AirSync | DevRev's product that syncs data between a customer's tools and DevRev. |
| Extraction | DevRev's word for pulling data in from the other system. |
| Data loading | DevRev's word for pushing changes out to the other system. |
| Identity mapper | A store that links external ids to DevRev ids. |
| Loop prevention | Stopping my own change from bouncing back and forth. |
| Workato recipe | An automation workflow in the Workato tool. |
| Feature flag | A switch that turns a feature on or off without a deploy. |

**Say it in one breath:** I built a mock-vendor two-way sync that maps closely onto AirSync's ideas, my one real third-party work was a Workato request and response integration, and I know exactly what I have not built.

---

## Mix-ups to avoid

- Do not say the drill signs the delivery id. The TypeScript and Python drills sign `timestamp.body`. My Go code signs `timestamp.id.body`.
- Do not mix up 202 for a duplicate with 500 for a database failure. One stops retries. The other asks for them.
- Do not call the echo memory the thing that ends loops. Single-writer fields and the origin filter also end them.
- Do not say exactly-once. It is at-least-once plus idempotent, version-gated writes.
- Do not say "extractor" and "loader" are DevRev terms. DevRev says extraction and data loading.
- Do not treat `Retry-After` the same in Go and in the drill. Go waits the exact time. The drill uses it as a floor.

## What I built vs what I only know

**Built [L], against my own mock Jira only:**

- HMAC verify with a signed delivery id, a timestamp window and constant-time compare.
- A Postgres inbox with dedupe, a worker with `SKIP LOCKED`, and dead letters.
- Identity mapping, field ownership, the version gate and three echo guards.
- A loader with an idempotency key, 429 handling and jittered backoff.
- A resumable extractor with a time budget.
- 15 integration tests on real Postgres. Micro-benchmark of verify on an M2 Pro.

**Shipped [P]:** only the Workato/NetSuite invoices integration. It was request and response. It was not a webhook or two-way sync.

**Knowledge only [K] (verify before an interview):**

- DevRev AirSync details from README section 1: soft timeout, hard kill, `isTimeout`, mappers, `external_versions`, `delay`.
- Standard Webhooks, Stripe and Slack signing schemes. These are from memory.
- SQS FIFO dedupe window.

**Not built:** secret rotation, an extraction lock, dead-letter replay tooling, metrics or tracing, outbound deletes and creates, and a reconcile job. The Lambda was never applied to AWS, and nothing drains its inbox.

**No claims on:** throughput, conflict rates, dead-letter rates, or a real vendor's behaviour.
