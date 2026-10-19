# DevRev FDE coding drills

Target: write each of these cold on a whiteboard, in TypeScript or Python, and explain it in 2 minutes. Every solution is small on purpose (13 to 110 lines of source). Tests are the spec; read them after you attempt the drill, not before.

Run commands: see [README.md](README.md).

## What the JD maps to

| JD theme | Drills |
| --- | --- |
| Webhooks | 3 (verify), 8 (echo loop), 2 (retry on delivery) |
| Large-scale data sync | 5 (merge), 7 (resumable extract), 8 (two-way sync), 4 (diff) |
| Serverless (time limits, re-invocation) | 7, 2 |
| Data structures and algorithms | 4, 5, 6, 9 |

## Table of contents

1. [Token-bucket rate limiter](#1-token-bucket-rate-limiter)
2. [Retry with exponential backoff, full jitter, Retry-After](#2-retry-with-exponential-backoff-full-jitter-retry-after)
3. [Webhook signature verification](#3-webhook-signature-verification)
4. [Deep JSON diff and applyPatch](#4-deep-json-diff-and-applypatch)
5. [Merge and dedupe by key, latest version wins](#5-merge-and-dedupe-by-key-latest-version-wins)
6. [Graph drills: BFS levels, Kahn, cycle path, impact analysis](#6-graph-drills)
7. [Resumable paginated extractor under a time budget](#7-resumable-paginated-extractor-under-a-time-budget)
8. [Echo-loop guard for two-way sync](#8-echo-loop-guard-for-two-way-sync)
9. [LRU cache, and sliding-window log vs fixed-window counter](#9-lru-cache-and-sliding-window-log-vs-fixed-window-counter)
10. [Footguns found while building these](#10-footguns-found-while-building-these)

Conventions in every drill: clocks, sleepers and RNGs are injected, never read from globals. That is what makes the exact-boundary tests possible, and it is the first thing to say out loud ("I'll inject the clock so I can test the boundary").

---

## 1. Token-bucket rate limiter

**Interviewer says:** "Implement a rate limiter that allows bursts of up to N requests but sustains only one request per R milliseconds. `tryTake()` returns allowed, or denied with how long the caller should wait. I want to unit test it, so no real clock."

**Budget:** 10 minutes.

**Key insight:** Do not run a timer to refill. Refill lazily from elapsed time on each call. Store credit in milliseconds (one token costs `refillEveryMs` of credit) so all arithmetic is integer. Then `retryAfterMs = price - credit` is exact.

**Say this in the interview:** "State is two numbers per key: credit and last-seen timestamp. On each call I add the elapsed time as credit, cap it at capacity, then try to pay the price. If I can't pay, the retry-after is the shortfall. No background thread, O(1) time and space per key. Capacity is the burst size, `1/refillEveryMs` is the sustained rate. I use a monotonic clock and clamp negative elapsed time."

**Complexity:** O(1) time, O(1) space per key.

**Pitfalls:**
- Fractional tokens as floats. Measured here: `Math.ceil((1 - 0.999) * 1000)` is `2`, not `1`, because `(1 - 0.999) * 1000` is `1.0000000000000009`. That is a wrong `retryAfterMs` at the exact boundary.
- Wall clock (`Date.now()`, `time.time()`) jumps backwards on NTP adjustments. Use `performance.now()` / `time.monotonic()` in production, and clamp elapsed at 0 anyway.
- Not capping credit at capacity: an idle key accumulates an unbounded burst.
- On denial, resetting `last` without crediting the elapsed time: the caller never gets a token under steady polling.
- `cost > capacity` can never succeed; reject it instead of returning an infinite retry-after.

**Follow-ups:**
1. *"Make it work across 20 instances."* Move `{credit, last}` into a shared store and make the check-and-update one atomic operation: a Redis Lua script or a DynamoDB conditional update. Decide fail-open vs fail-closed when the store is down. For hot keys, take a batch of tokens locally and sync periodically, accepting some over-admission.
2. *"Token bucket vs leaky bucket vs sliding window?"* Token bucket admits bursts and bounds the average. A leaky bucket (as a queue) smooths the output rate and delays instead of rejecting. Sliding-window log is exact but costs O(limit) memory per key (drill 9).

**Files:** [ts/src/rateLimiter.ts](ts/src/rateLimiter.ts), [ts/test/rateLimiter.test.ts](ts/test/rateLimiter.test.ts), [py/fde/rate_limiter.py](py/fde/rate_limiter.py), [py/tests/test_rate_limiter.py](py/tests/test_rate_limiter.py)

---

## 2. Retry with exponential backoff, full jitter, Retry-After

**Interviewer says:** "Write a retry wrapper for calling a flaky HTTP API. Exponential backoff with full jitter, honour `Retry-After`, cap the attempts, and don't retry anything that isn't safe to retry. Make it testable."

**Budget:** 15 minutes.

**Key insight:** Three independent decisions.
1. *Whether* to retry: idempotency gate AND retryable class (429, 5xx, network) AND attempts left.
2. *How long* to wait: `floor(rng() * min(cap, base * 2^(attempt-1)))` (full jitter), then `Retry-After` acts as a floor: `max(jittered, hinted)`.
3. *Testability*: inject `sleep`, `rng`, `nowMs`. Then the tests assert exact sleep values.

**Say this in the interview:** "First I decide if a retry is even allowed: GET, PUT, DELETE are idempotent by definition (RFC 9110); a POST only if the caller gave an idempotency key, because a timeout doesn't tell me whether the server processed it. Then the error must be retryable: 429, 5xx or a network failure, never other 4xx. The delay is full jitter: uniform between zero and an exponentially growing ceiling that is capped. If the server sent `Retry-After`, in seconds or as an HTTP-date, I treat it as a minimum. Sleep, RNG and clock are injected so the tests assert exact numbers. After the last attempt I rethrow the last error and don't sleep."

**Complexity:** O(attempts) time, O(1) space. Total wait is bounded by `sum(min(cap, base * 2^k))`, plus any `Retry-After` hints.

**Pitfalls:**
- Retrying a non-idempotent POST that may already have succeeded creates duplicates.
- No jitter: all clients retry in lockstep (thundering herd).
- `Retry-After` has two formats (delay-seconds, HTTP-date). JavaScript's `Date.parse("foo 3")` returns a valid date, so gate the date branch on the strict IMF-fixdate shape (tested). Cap digit length too (Python's `int()` throws on 4300+ digit strings).
- Sleeping after the final attempt, or off-by-one on `maxAttempts` (it is total attempts, including the first).
- Unbounded exponent: `2 ** attempt` reaches `Infinity` in JS. Clamp with `min(cap, ...)`.
- Retrying at every layer multiplies load (3 layers x 3 attempts = 27 calls). Retry at one layer.
- Honest limit of this drill: `Retry-After` is a floor with no ceiling.

**Follow-ups:**
1. *"`Retry-After: 3600` inside a 15-minute Lambda?"* Don't sleep. Either give up and surface the error so the queue redelivers later (delay or visibility timeout), or add `maxWaitMs` and throw when the hint exceeds it. Sleeping burns billed time.
2. *"Why full jitter rather than equal or decorrelated jitter?"* The AWS Architecture Blog post "Exponential Backoff And Jitter" compares them; my recollection is that it favours full jitter on total work and completion time. I am not certain of the details, so verify before quoting it.

**Files:** [ts/src/retry.ts](ts/src/retry.ts), [ts/test/retry.test.ts](ts/test/retry.test.ts), [py/fde/retry.py](py/fde/retry.py), [py/tests/test_retry.py](py/tests/test_retry.py)

---

## 3. Webhook signature verification

**Interviewer says:** "We deliver events by POSTing JSON to your endpoint, with a timestamp header and a signature header. Write the verification. What can go wrong?"

**Budget:** 15 minutes.

**Key insight:** Sign bytes, not objects. The MAC is `HMAC-SHA256(secret, "<timestamp>." + rawBodyBytes)`. The timestamp is inside the MAC so it can't be re-stamped. The tolerance window bounds replay. The comparison is constant-time. Order of checks: missing headers, malformed timestamp, window, then MAC.

**Say this in the interview:** "I verify against the exact bytes received, never a parsed-and-reserialised body, because the same JSON can have different bytes. I concatenate the timestamp, a dot, and the raw body bytes, HMAC-SHA256 it with the shared secret, and compare to the header in constant time so I don't leak how many leading bytes matched. The timestamp is part of the signed material, so an attacker can't replay an old body under a fresh timestamp. I also reject timestamps outside a tolerance window in either direction. Failure returns a typed reason for logs and tests; the HTTP response to the sender should stay a generic 401. In TypeScript I use Web Crypto so the same code runs on Node, Lambda and Cloudflare Workers."

**Complexity:** O(body length) time, O(body length) space for the concatenated message.

**Pitfalls:**
- Body parsers that parse then re-stringify. The re-serialised JSON test proves same data, different bytes, signature fails. In Express you need the raw body (for example `express.raw`) on that route.
- `request.text()` decodes as UTF-8 and can corrupt non-UTF-8 bytes. Use `arrayBuffer()`; the binary-safe test covers this.
- API Gateway proxy events can carry a base64 body (`isBase64Encoded`). Decode before verifying.
- `===` or `==` on signatures leaks timing. Use a constant-time compare (`hmac.compare_digest` in Python; an XOR-accumulate loop over equal-length bytes in TS).
- Timestamp not covered by the MAC, or no window: replay forever.
- A window is not deduplication. A replay inside the window still verifies; dedupe on the event id.
- Python `\d` matches Unicode digits and `str.isdigit()` accepts `"²"`. The drill uses `[0-9]` (tested with Arabic-Indic digits).
- Secret rotation: accept signatures from both old and new secrets during the overlap.

**Honest limits:** I do not know DevRev's actual signing scheme (header names, encoding, tolerance). This drill uses the common `timestamp.body` pattern; check their docs. I am not certain whether Web Crypto's `subtle.verify` is guaranteed constant-time in every runtime, which is why the drill uses an explicit compare. Cloudflare Workers has a non-standard `crypto.subtle.timingSafeEqual` as far as I recall; verify in the current docs before relying on it.

**Follow-ups:**
1. *"A replay arrives inside the 5-minute window."* Store the event or delivery id in a TTL store with a conditional put (TTL at least the tolerance) and drop duplicates; better, make the handler idempotent so duplicates are harmless anyway.
2. *"Why `crypto.subtle` and not `node:crypto`?"* Web Crypto is the common denominator across Node (global), Workers and browsers. `node:crypto` may need a compatibility flag on Workers; verify current docs. In Python the stdlib `hmac` is enough.

**Files:** [ts/src/webhook.ts](ts/src/webhook.ts), [ts/test/webhook.test.ts](ts/test/webhook.test.ts), [py/fde/webhook.py](py/fde/webhook.py), [py/tests/test_webhook.py](py/tests/test_webhook.py)

---

## 4. Deep JSON diff and applyPatch

**Interviewer says:** "Given two JSON documents, produce the list of field-level changes, each with a path, an operation (add, remove, replace) and the before and after values. Then write `applyPatch` so that `apply(diff(a, b), a)` equals `b`."

**Budget:** 20 minutes for `diff`, 10 for `applyPatch`, 10 for the property test.

**Key insight:** Recurse while both sides have the same kind (object, array); the moment kinds or scalars differ, emit one `replace` at that path. Arrays are compared by index; removals are emitted from the tail so the changes can be applied one after another without index shifting. `applyPatch` clones then mutates, and a one-slot holder lets a root-path change reuse the same code. The property test (`apply(diff(a,b), a) == b` over thousands of seeded random pairs) is the specification.

**Say this in the interview:** "Objects: keys only in `before` are removes, keys only in `after` are adds, shared keys recurse. Arrays: I diff by index, add the extra tail elements, and remove surplus elements from the end backwards so the patch stays valid when applied sequentially. Different types or different scalars: replace at that path. The trade-off is that index diffing is O(n) and trivial but inserting at the front of an array rewrites every element; for arrays whose items have ids I'd match by key instead. To trust it I'd write a property test with a seeded generator."

**Complexity:** O(size of both documents) time; output size is the number of changed leaves; recursion depth equals document depth.

**Array trade-off (by index vs keyed):**
- By index: simple, linear, stable output for append and truncate. Inserting or deleting near the front makes every later element look edited, and moved items look like edits plus adds. See the "inserting at the front" test.
- Keyed (match items by `id`): minimal and semantic ("comment 7 edited"), good for audit trails. It needs a key contract and a separate story for ordering.
- Unkeyed and minimal: LCS or Myers diff, more code and O(n*m) or O(ND) work.

**Pitfalls:**
- `key in obj` is true for inherited names like `toString`; use `Object.hasOwn` (tested in both directions).
- Python: `True == 1` and `1 == True`, so a naive `!=` misses `1 -> true`. The drill compares a JSON "kind" first (tested).
- Mutating the input, or aliasing the patch's `after` subtree into the result (tested both).
- Patches from untrusted input and `__proto__` path segments: the TS `applyPatch` refuses them (tested). Python has no equivalent hazard.
- `null` vs missing key are different; `undefined` and `NaN` are not JSON.
- Removing array items front to back shifts later indices.

**Follow-ups:**
1. *"Emit standard JSON Patch?"* Same three operations; render the path as a JSON Pointer (RFC 6901: escape `~` as `~0` and `/` as `~1`) and the patch as RFC 6902. Use its `test` op for preconditions.
2. *"The documents are 10 MB, or millions of records?"* Don't deep-diff everything. Compare per-record by version or `updated_at` first and deep-diff only changed records, or hash subtrees (Merkle-style) to skip equal ones.

**Files:** [ts/src/jsonDiff.ts](ts/src/jsonDiff.ts), [ts/test/jsonDiff.test.ts](ts/test/jsonDiff.test.ts), [py/fde/json_diff.py](py/fde/json_diff.py), [py/tests/test_json_diff.py](py/tests/test_json_diff.py)

---

## 5. Merge and dedupe by key, latest version wins

**Interviewer says:** "Records arrive from several pages and sources, with duplicates. Keep exactly one record per id, the one with the highest version. Say what happens on a tie. Keep the output order stable. Linear time."

**Budget:** 8 minutes.

**Key insight:** One pass with a hash map. Overwriting an existing key in a JS `Map` or Python `dict` keeps its original insertion slot, so output is ordered by first appearance for free. The tie-break is one operator: `>=` means the later record wins, `>` means the earlier wins. Pick one and say it aloud.

**Say this in the interview:** "Single pass, map from key to the current winner. For each record, if the key is new or its version is greater than or equal to the winner's, it replaces the winner. Using `>=` makes ties go to the later arrival, which I'd document as the rule. Insertion order of the map gives me stable output ordered by first appearance. O(n) time, O(distinct keys) space, no sort."

**Complexity:** O(n) time, O(k) space for k distinct keys. The test counts calls: one `key()` per record, at most two `version()` per record.

**Pitfalls:**
- Sort-then-dedupe is O(n log n) and scrambles original order unless the sort is stable.
- Unspecified tie-break gives non-reproducible output when sources arrive concurrently.
- Comparing versions as strings (`"10" < "9"`).
- Mixing `updatedAt` from different machines' clocks as the version.
- Deletes: a tombstone needs a version too, or a stale create arriving later resurrects the record.
- Using `None`/`undefined` as the "missing" check when records themselves can be falsy.

**Follow-ups:**
1. *"The data doesn't fit in memory."* Partition by `hash(key)` into shards that do fit, merge per shard, or external-sort by key then take the max per run. LSM-style compaction is the production version.
2. *"Out-of-order deletes?"* Keep tombstones as versioned records and only garbage-collect them after the longest possible reordering window.

**Files:** [ts/src/mergeRecords.ts](ts/src/mergeRecords.ts), [ts/test/mergeRecords.test.ts](ts/test/mergeRecords.test.ts), [py/fde/merge_records.py](py/fde/merge_records.py), [py/tests/test_merge_records.py](py/tests/test_merge_records.py)

---

## 6. Graph drills

**Interviewer says (four parts, same graph):**
- A. "List the tickets reachable from X grouped by distance."
- B. "Given dependencies, give me a valid order to do them, or tell me it's impossible."
- C. "If there's a cycle, show me one."
- D. "Which tickets are impacted by X through any chain of links, at most N hops away?"

**Budget:** BFS 8, Kahn 10, cycle path 12, impact 5 (it reuses BFS).

**Key insight:** One discipline for all four: a visited or state set guarantees termination, and a level-by-level frontier gives distances. Mark visited when you *enqueue*, not when you dequeue. Kahn peels indegree-0 nodes; if you can't peel everything, a cycle exists, but Kahn can't tell you which one. For the path, DFS with two states (visiting, done): the DFS stack at the moment you see a `visiting` node IS the cycle. Impact analysis is BFS with a depth cap, dropping level 0.

**Say this in the interview:** "For BFS I keep a frontier array and a seen set; I add to `seen` when I discover a node so it can't be queued twice, and each loop iteration is one level. For ordering I use Kahn's algorithm: compute indegrees over every node including ones that only appear as targets, start with the zeros, and as I pop a node I decrement its targets. If the output is shorter than the node count there's a cycle. To return the cycle I run an iterative DFS with an explicit stack so deep graphs don't overflow; hitting a node that's still on the stack gives me the path. Impact analysis is just BFS stopping after N levels."

**Complexity:** BFS, Kahn and cycle detection are O(V + E) time and O(V) space. Impact with a depth cap is bounded by the nodes and edges within N hops.

**Pitfalls:**
- Marking visited on dequeue: the same node can sit in the queue many times.
- `Array.shift()` as a queue: measured here, draining 200,000 items with `shift()` took about 3.1 s (Node 24.6). Use an index pointer (TS) or `deque` (Python).
- Recursive DFS overflows the stack on deep chains (about 1000 frames in default Python; far fewer than 200k in JS). The tests build a 200,000-node chain.
- Indegree computed only from map keys misses nodes that appear only as targets.
- Plain-object adjacency breaks on keys like `constructor` or `__proto__`; the TS version takes a `Map`.
- Edge direction: "blocks" is directed; "relates to" is symmetric, so add both edges (`buildGraph(edges, false)`).
- A self-loop is a cycle. A diamond is not.
- The depth cap must stop expanding, not just filter the output.
- Hub nodes make the result huge; consider a result-size cap as well.

**Follow-ups:**
1. *"50 million edges, can't load the graph."* Run BFS one level per batched query (`WHERE from IN (frontier)`), so the depth cap means at most N queries. Keep visited in a set or bitset; avoid a Bloom filter for visited unless you accept dropped nodes from false positives.
2. *"Smallest-id-first topological order?"* Replace the FIFO queue with a min-heap: O((V + E) log V).

**Files:** [ts/src/graph.ts](ts/src/graph.ts), [ts/test/graph.test.ts](ts/test/graph.test.ts), [py/fde/graph.py](py/fde/graph.py), [py/tests/test_graph.py](py/tests/test_graph.py)

---

## 7. Resumable paginated extractor under a time budget

**Interviewer says:** "We need to export millions of tickets from a vendor API, one page at a time, from a serverless function with a hard time limit. The function will be killed and re-invoked. Write the extraction loop so every invocation makes progress and nothing is lost or duplicated."

**Budget:** 25 minutes.

**Key insight:** Four invariants.
1. Check the remaining budget BEFORE starting a page, with room for the slowest page seen so far. Never start work you can't finish.
2. Order per page: fetch, write to the sink, then save the checkpoint. A crash replays at most one page (at-least-once). Checkpointing first would lose a page.
3. Replaying a page is safe only if the consumer's write is an idempotent upsert keyed by entity id. At-least-once delivery plus idempotent upsert is effectively-once.
4. A positive budget always processes at least one page, so a too-small budget can't livelock. The result carries the checkpoint so the scheduler re-invokes.

**Say this in the interview:** "The loop is: compute remaining time; if it's zero or less than the slowest page I've seen, stop cleanly and return the checkpoint; otherwise fetch the page, upsert it into the sink, persist the cursor, repeat. I persist after every page, so a crash costs at most one replayed page, and because the sink upserts by id, the replay doesn't change the result. I save an explicit `done` flag because a null cursor is ambiguous between 'start' and 'finished'. The next invocation loads the checkpoint and calls the same function."

**Complexity:** O(pages processed) per invocation; one checkpoint write per page. Memory is one page.

**Pitfalls:**
- Checkpoint before write: a crash loses that page silently.
- Append-only sink: the replay duplicates exactly one page (the test shows `TOTAL + PAGE_SIZE` rows, then shows the upsert fixes it).
- Checking elapsed time after the page: overruns the platform limit (AWS Lambda hard-caps at 15 minutes).
- Budget smaller than one page and a strict "fits?" rule means zero progress forever.
- Offset pagination while the data changes skips or duplicates rows; prefer opaque cursors. Cursors can expire.
- Two concurrent invocations for the same job: take a lease or write checkpoints with a conditional version check.
- A hung `fetchPage` ignores the budget; add a per-request timeout (`AbortSignal.timeout`).
- A 429 inside `fetchPage` should be handled by the retry wrapper from drill 2.

**Follow-ups:**
1. *"Is this exactly-once?"* Not end to end. It is at-least-once delivery plus an idempotent upsert, which gives effectively-once. Make the upsert key deterministic and guard with a version (drill 5) so a replayed older page can't overwrite newer data.
2. *"Many tenants, or parallelise?"* Shard by tenant or key range, each shard with its own checkpoint, fan out through a queue, and share one global rate limiter (drill 1) so the vendor limit is respected. Ordering across shards isn't guaranteed.

**Notes:** the Python version is synchronous; the TS version is async because its I/O is. The tests cover the crash matrix (crash after fetch, mid-upsert, before checkpoint, on every page index) and 17 budget values around the page-cost boundaries.

**Files:** [ts/src/extractor.ts](ts/src/extractor.ts), [ts/test/extractor.test.ts](ts/test/extractor.test.ts), [py/fde/extractor.py](py/fde/extractor.py), [py/tests/test_extractor.py](py/tests/test_extractor.py)

---

## 8. Echo-loop guard for two-way sync

**Interviewer says:** "We sync tickets both ways between our system and DevRev. When we write to DevRev, DevRev fires a webhook back at us. How do you stop infinite ping-pong, and how do you notice real conflicts?"

**Budget:** 15 minutes.

**Key insight:** Keep a ledger from entity id to the fingerprint of what we last pushed (and set it when we apply a remote change too, since the remote now has that content). Fingerprint a canonical form of only the synced fields so key order doesn't matter. Then the decision for an incoming change is a three-row table:

| Condition | Decision |
| --- | --- |
| incoming equals the ledger entry, or equals our local copy | `drop-as-echo` |
| otherwise, local equals the ledger entry (we haven't changed since the last sync) | `apply` |
| otherwise (both sides changed) | `conflict` |

**Say this in the interview:** "A webhook that carries exactly what I last pushed is my own echo, so I drop it. If it differs and my local copy still matches what I last pushed, it's a genuine remote edit, so I apply it and record it in the ledger so my change detector doesn't push it straight back. If it differs and my local copy also moved, both sides edited: that's a conflict I surface instead of overwriting. The test harness runs the loop with and without the guard: guarded settles in one or two steps, unguarded runs until the step cap."

**Complexity:** O(1) per decision; O(entities) ledger, ideally persisted next to the entity.

**Pitfalls:**
- Comparing timestamps or actors instead of content: clock skew, and webhooks don't reliably say who wrote.
- Fingerprinting fields the remote mutates (`updated_at`, normalised whitespace): the echo never matches and the loop never stops. Hash only the fields you sync.
- Order-dependent serialisation of the fingerprint.
- Not updating the ledger on apply: the change detector pushes the applied change straight back.
- Losing the ledger on restart: expect one duplicate round trip, and conflicts misclassified until it refills.
- Known limitation, documented by a test: an old echo arriving after a newer push (`v1` after `v2`) is mistaken for a remote edit.

**Follow-ups:**
1. *"Echoes arrive late or out of order."* Store the remote version or etag returned by the push response and drop any incoming event whose remote version is not newer than the last one we pushed, or keep a short TTL set of recently pushed fingerprints per entity. A version is more reliable than content when the remote normalises data.
2. *"What's the conflict policy?"* Options: last-writer-wins by remote `updatedAt` (silently loses an edit), field-level three-way merge using the last-synced snapshot as the base (needs the snapshot, not just a hash), or route to a human. Choose per field class.

**Files:** [ts/src/echoGuard.ts](ts/src/echoGuard.ts), [ts/test/echoGuard.test.ts](ts/test/echoGuard.test.ts), [py/fde/echo_guard.py](py/fde/echo_guard.py), [py/tests/test_echo_guard.py](py/tests/test_echo_guard.py)

---

## 9. LRU cache, and sliding-window log vs fixed-window counter

**Interviewer says (two questions):**
- A. "Implement an LRU cache with O(1) `get` and `put`."
- B. "Allow N requests per minute per user. Implement a fixed-window counter and a sliding-window log, and show me where the fixed window breaks."

**Budget:** LRU with Map or OrderedDict 12 minutes; with a hand-written linked list 20 minutes; both windows 10 minutes.

**Key insight:**
- LRU = hash map for lookup plus an ordering for eviction. JS `Map` and Python `OrderedDict` remember insertion order, so "delete and re-insert" (or `move_to_end`) is move-to-front and the first key is the least recent. If the interviewer bans that, use a doubly linked list with sentinel head and tail plus a `key -> node` map, so unlinking a node is O(1). Both versions are in the repo and run the same tests.
- Fixed window counts per aligned window and resets at the edge, so a client can send N just before and N just after the edge: 2N in a moment. The sliding log keeps timestamps and evicts those at or older than `now - window`, so the limit holds over any window.

**Say this in the interview:** "LRU: map for lookup, recency order for eviction. `get` and `put` both move the key to most-recent; when size exceeds capacity I drop the least recent. All O(1). With a hand-rolled list I use sentinel nodes so there are no null checks on unlink. For rate limiting: a fixed-window counter is O(1) memory but allows a double burst at a window edge; I'll show it in a test. A sliding log fixes that at O(limit) memory per key, and I only log allowed requests."

**Complexity:** LRU `get`/`put` O(1). Fixed window O(1) time and space per key. Sliding log amortised O(1) time, O(limit) space per key.

**Pitfalls (LRU):** forgetting that `get` counts as a use; an overwrite must move to front and must not evict; capacity below 1; a stored `undefined`/`None` value is indistinguishable from a miss in this API; in the linked version, forgetting to delete the evicted key from the map; thread safety (JS is single-threaded, Python threads need a lock).

**Pitfalls (windows):** inclusivity at the boundary (this drill: an entry exactly `window` old has expired); logging denied requests extends the lockout (tested); fixed windows aligned to the epoch, not to the first request (tested); `Array.shift()` is O(n) but n is at most the limit here, so use a deque or ring buffer if the limit is large (Python uses `deque`).

**Follow-ups:**
1. *"The sliding log costs O(limit) per user. Alternative?"* Sliding-window counter: keep the current and previous window counts and estimate `prev * (1 - elapsedFraction) + current`. O(1) memory; it assumes requests were uniform in the previous window. A token bucket (drill 1) is the other O(1) option. In Redis the exact log is usually a sorted set trimmed by score.
2. *"LRU with TTL, or distributed?"* TTL: store an expiry per entry, evict lazily on `get` and with a periodic sweep. Distributed: Redis can evict by LRU policy, but as far as I recall it approximates LRU by sampling; verify in the Redis docs before quoting.

**Files:** [ts/src/lru.ts](ts/src/lru.ts), [ts/test/lru.test.ts](ts/test/lru.test.ts), [ts/src/slidingWindow.ts](ts/src/slidingWindow.ts), [ts/test/slidingWindow.test.ts](ts/test/slidingWindow.test.ts), [py/fde/lru.py](py/fde/lru.py), [py/tests/test_lru.py](py/tests/test_lru.py), [py/fde/sliding_window.py](py/fde/sliding_window.py), [py/tests/test_sliding_window.py](py/tests/test_sliding_window.py)

---

## 10. Footguns found while building these

Each of these hit a test or was verified by running it here.

| Language | Footgun | Where it bit |
| --- | --- | --- |
| JS | `Date.parse("foo 3")` returns a valid date | `Retry-After` parsing (2) |
| JS | `"toString" in {}` is `true`; use `Object.hasOwn` | JSON diff (4) |
| JS | `arr.shift()` in a loop is quadratic: 200k items took about 3.1 s | BFS and Kahn queues (6) |
| JS | `(1 - 0.999) * 1000` is `1.0000000000000009` | token bucket (1) |
| JS | `request.text()` can corrupt non-UTF-8 bodies | webhook (3) |
| Python | `True == 1`, so `1 != True` is `False` | JSON diff (4) |
| Python | `\d` matches Unicode digits; `"²".isdigit()` is `True` | webhook timestamp (3) |
| Python | `int("9" * 5000)` raises (4300-digit limit) | `Retry-After` and timestamp parsing (2, 3) |
| Python | default recursion limit about 1000 | cycle detection (6) |
| Both | float time arithmetic at exact boundaries | rate limiter, windows, extractor |

## How to use this

1. Read the statement and the budget only. Whiteboard it (or type it with the file closed) against the clock.
2. Say the "say this" paragraph out loud without reading it.
3. Run only that drill's tests. Compare the failing cases against the pitfalls list.
4. Answer the two follow-ups out loud before reading them.
5. Redo the drills you needed more than the budget for, in the other language.
