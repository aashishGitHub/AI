# Scenarios 02 — RAG and vector search

Source module: [`../02-rag-and-vector-search.md`](../02-rag-and-vector-search.md). Six real-time situations an FDE meets, laddered 🟢 🟢 🟡 🟡 🔴 🔴.

How to use: read only the **Situation**, answer out loud, then compare. Every number in a Situation is an **example**. Numbers from my own runs are marked "from my notes" and are single samples on one machine.

Lanes: **[P]** shipped at Couchbase (Ask AI is Couchbase's system; I am a contributor and know it through its design document, so I describe it and never quote its code) · **[L]** my own lab build, never deployed to a customer · **[K]** knowledge only, not built.

| # | Level | Failure mode |
|---|---|---|
| 1 | 🟢 | The model invents syntax for something the docs do not cover |
| 2 | 🟢 | Retrieval fails and the answer silently becomes ungrounded |
| 3 | 🟡 | Exact identifiers (error codes) are not found by vector search |
| 4 | 🟡 | A chunk boundary cuts a code block, so the answer is half a script |
| 5 | 🔴 | Embedding model mismatch between write path and read path |
| 6 | 🔴 | Corpus grows 100x: latency, memory, and silent recall loss |

---

## Scenario 1 🟢 The bot invents `CREATE VECTORS ON ...` for a feature the docs do not cover

**Situation.** Monday 11:20, a customer's developer-relations team is piloting a docs assistant (example). A user asks "How do I create a vector index?" The corpus only covers primary indexes. The bot answers with a confident, fluent, wrong statement and cites nothing.

**Level.** 🟢 Beginner.

**What's being tested.** Grounding is a prompt contract: the model must be told that it is allowed to say "I do not know". Also, that refusal is not a retrieval gate.

**Clarifying questions to ask first.**
1. What system prompt is actually sent to the model, and who owns it (server or client)?
2. Does the prompt give an exact permitted refusal sentence?
3. What did retrieval return for this question: how many chunks, which ones?
4. Does a negative test (an unanswerable question) exist in the golden set?

**Flow of control and data.**

```
question ─▶ retriever (always returns top K, even for an unanswerable question)
        └─▶ buildMessages: numbered chunks + server-owned system prompt
        └─▶ model ─▶ answer OR the permitted refusal sentence
```

**Diagnosis steps.**
1. Log or print the assembled messages for this request. Is the system prompt the grounded one or the "no corpus" one?
2. Read the retrieved chunks. In my lab retrieval returns the top K (4 of 6 chunks) for both an answerable and an unanswerable question, so refusal cannot come from retrieval.
3. Check the prompt for the refusal rule: "If the context does not contain the answer, reply exactly ...".
4. Run the negative golden row against the model. Confirm it fails without the rule.
5. Check completion tokens. A refusal is short (from my notes, 9 tokens against 128 to 162 for a grounded answer, single samples).

**Fix now vs fix properly.**
- Now: add the explicit permitted refusal sentence and the no-invention rule to the server prompt. A prohibition with no permitted alternative is a trap.
- Properly: keep a negative row in the golden set with deterministic checks (a closed list of decline phrases, plus a guard for the observed bad string), and consider a score threshold on retrieval, which means changing the "empty chunks selects the ungrounded prompt" branch.

**How you'd test it.** A golden row for each unanswerable class. Assertion: output contains one of the decline phrases and does not contain the invented syntax. Run on every prompt change.

**Spoken answer (60-90 seconds).**
I would look at the exact messages the model received, because grounding lives in the prompt. In my build, before retrieval and the right prompt, a 1B model answered "how do I create a vector index" with an invented `CREATE VECTORS ON` statement three runs in a row. With retrieval plus one line telling it that it may decline with a fixed sentence, the same model said the documentation does not cover this. So the fix was one sentence, not a bigger model. I would also point out that retrieval returned four chunks even for the unanswerable question, so the refusal is a prompt contract and not a retrieval decision. I would be careful about the claim: that is one small model, a six-chunk corpus and two golden cases, and I did not compare against fine-tuning or long context. For the customer I would add a negative row per unanswerable class so the next prompt change cannot reintroduce it.

**Follow-ups the interviewer will ask.**
- *What if a retrieved chunk itself contains instructions?* Delimit chunks as data, say so in the prompt, keep tools and secrets out of that prompt. My build does not sanitise chunks, which is fine for first-party docs, not for customer tickets. Measure with an injection set.
- *When is RAG the wrong tool?* Exact lookups and aggregations ("status of ticket 4821", "tickets closed last week") belong to a structured query.
- *Can the model cite a source that does not exist?* Yes. Citations are requested by the prompt and I do not validate `[n]` against the sources list. Parse and check it.

**Tie to your code.** [L] grounded prompt and `buildMessages` in [`fe-hands-on/server/stream.go`](../../../../fe-hands-on/server/stream.go), negative golden row in [`evals/promptfooconfig.yaml`](../../../../evals/promptfooconfig.yaml).

---

## Scenario 2 🟢 The vector store blips and users get confident answers with no evidence

**Situation.** Friday 16:20 (example). The vector query errors intermittently for about 12 minutes. Users report answers that are fluent but different from what the docs say, and the sources panel is empty or unrelated. Latency looks normal.

**Level.** 🟢 Beginner.

**What's being tested.** Fail loudly. A silent fallback to an ungrounded or pseudo-grounded answer is the dangerous path in RAG.

**Clarifying questions to ask first.**
1. When retrieval throws, what does the handler do: error, fallback search, or answer anyway?
2. If there is a fallback, is it still grounded and is it observable (logged, counted)?
3. Does the UI receive an explicit error event, or just fewer tokens?
4. Is the same code path used by a prototype and the current service?

**Flow of control and data.**

```
POST /api/chat ─▶ HandleChat ─▶ retriever.Retrieve ──ok──▶ sources frame ─▶ provider.Stream ─▶ done
                                       └─error──▶ log + error frame ─▶ STOP (provider never called)
prototype: vector query error ─▶ LIKE '%query%' fallback ─▶ similarity reported as 1.0 (hides the failure)
```

**Diagnosis steps.**
1. Grep logs for the retrieval failure line and count them over the window.
2. Count responses with zero sources frames and compare to request count.
3. In the prototype, search for the console line "Falling back to text search..." and note that every result carries a constant similarity.
4. Check whether a provider call happened after a failed retrieval. It must not.

**Fix now vs fix properly.**
- Now: make retrieval failure an `error` event and return. No fallback to the model's memory.
- Properly: a fallback is acceptable only if it stays grounded and is observable. Log which search type served the request and alert on fallback rate. Never fake a similarity score.

**How you'd test it.** A handler test with a stub retriever that returns an error and a stub provider. Assert exactly one `error` frame, the error names the cause, and the provider was never called. That test exists in my service.

**Spoken answer (60-90 seconds).**
I would first ask what the handler does when retrieval throws, because that decides whether this is an outage or a quality incident. My current Go service sends one error frame and returns without calling the model, and a test asserts the provider is never called, because answering ungrounded without saying so is the worst path. My earlier Node prototype did the opposite: on a vector query error it fell back to a `LIKE` text search and reported a constant similarity of 1.0, which hides the failure behind a fake score. The principle I hold is that a fallback is fine if it is still grounded retrieval and it is visible in logs and metrics, and not fine if it pretends nothing happened. For the customer I would add a counter for retrieval errors and fallbacks, and an alert on the rate. Ask AI, per its design document, falls back to pure vector search when hybrid returns nothing and logs which type was used. That is a visible degradation.

**Follow-ups the interviewer will ask.**
- *Why emit sources before tokens?* The reader sees evidence while the answer streams, and it proves the citations come from the same chunks that went into the prompt.
- *What if the client disconnects mid-stream?* Log it, stop, and let context cancellation abort the upstream generation so tokens nobody reads are not paid for.
- *Does your service have a health check for the dependency?* Yes for the model provider (503 and `degraded`). I did not add one for the vector store because it is in memory.

**Tie to your code.** [L] [`fe-hands-on/server/stream_test.go`](../../../../fe-hands-on/server/stream_test.go) (retrieval failure test), [`fe-hands-on/server/stream.go`](../../../../fe-hands-on/server/stream.go), prototype fallback in [`RAG-app/server/couchbase.js`](../../../../../RAG-app/server/couchbase.js).

---

## Scenario 3 🟡 Support searches `ERR-4012` and gets generic troubleshooting pages

**Situation.** Tuesday 13:05 (example). A customer's support agents paste an error code and a few words into the assistant. The page that documents that exact code exists in the corpus, but the top 4 chunks are general "index build is slow" pages. Paraphrased questions work fine.

**Level.** 🟡 Intermediate.

**What's being tested.** The weakness of dense-only retrieval on exact tokens, and where hybrid search and fusion plug in without rewriting the service.

**Clarifying questions to ask first.**
1. Is the right chunk in the candidate pool at all, for example the top 50, or only missing from the top K?
2. Does the chunk text contain the exact code string, or was it lost in chunking?
3. What does a keyword search over the raw corpus return for the same query?
4. Is there a golden retrieval set with queries of this kind and a recall@K number?

**Flow of control and data.**

```
query ─▶ dense retriever (embedding) ──────┐
     └─▶ sparse retriever (BM25 / keyword) ┴─▶ fuse by RANK (RRF) ─▶ top K ─▶ prompt
                       both behind the same Retriever interface
```

**Diagnosis steps.**
1. Raise K (or the fanout) for this query and see whether the right chunk appears at all. Not in the pool means recall; in the pool but low means ranking.
2. Run a plain keyword search over the corpus for `ERR-4012`. If it finds the page, dense retrieval is the weak link.
3. Print the chunk that should match and confirm the code string survived chunking.
4. Check ranks from each retriever separately before fusing.

**Fix now vs fix properly.**
- Now: a keyword lookup path for identifier-shaped queries (exact string match first), with the dense result as fallback.
- Properly: a hybrid retriever that composes a dense and a sparse retriever and fuses by reciprocal rank (score is the sum of 1 over (k plus rank), k conventionally 60, verify for your data). Ranks are used because cosine and BM25 scores are on different scales. Then a golden retrieval set and ablations on any re-ranking heuristic.

**How you'd test it.** A golden retrieval set with labelled relevant chunk ids per query, including identifier queries, measured as recall@K before and after. A unit test with two stub retrievers that agree on one chunk: it must rise to the top after fusion.

**Spoken answer (60-90 seconds).**
First I check whether the right chunk is in the candidate pool, because a re-ranker can only reorder what the retriever returned. I would run a plain keyword search for the code, and if that finds the page then I know dense search is blurring an identifier that has little learned meaning. The fix I would propose is hybrid search: run dense and keyword retrieval, merge by rank using reciprocal rank fusion, and keep the stable tie-break so evals can be diffed. I would do it behind my existing `Retriever` interface so nothing above it changes. I need to be clear about my lane: my build is dense only, and hybrid exists only as a scratch snippet I compiled and tested in a copy, not committed. Ask AI does hybrid search in one Couchbase query with a heuristic re-ranker, per its design document, and I did not build or measure that. I would not claim the improvement until a golden retrieval set shows recall@K before and after.

**Follow-ups the interviewer will ask.**
- *Why ranks and not scores?* Scores from different retrievers are not comparable.
- *The right document is ranked 14th and never reaches the prompt. What now?* Retrieve wider, re-rank to a short list, cheap heuristic first, a cross-encoder only if measured quality justifies it.
- *Ask AI falls back silently when hybrid is empty. Is that your prototype's bug?* No. It stays grounded and logs the search type. The prototype faked a score.

**Tie to your code.** [L] the `Retriever` seam in [`fe-hands-on/server/retriever.go`](../../../../fe-hands-on/server/retriever.go) and its stable tie-break. [K] hybrid and RRF (module 02 has the Illustrative snippet, not in the repo). [P] hybrid and re-ranker in the Ask AI design document, [`docs/Ask AI design document.md`](../../../../docs/Ask%20AI%20design%20document.md), section 4.4.5.

---

## Scenario 4 🟡 The answer gives the first half of a deploy script and stops

**Situation.** Wednesday 15:40 (example). A user asks for the full set of steps to configure a service. The answer shows the first few commands and ends. The documentation page has the whole script in one fenced code block.

**Level.** 🟡 Intermediate.

**What's being tested.** Chunking sets the ceiling on retrieval quality. Diagnosing whether a bad answer is a chunking problem, an index problem or a generation problem.

**Clarifying questions to ask first.**
1. What does the stored chunk text look like for that page: one block or two pieces?
2. Does the script contain lines starting with `#` (shell comments) or blank lines inside the fence?
3. Were both halves retrieved, or only one of two chunks?
4. What is the chunk budget, and is it in characters or tokens?

**Flow of control and data.**

```
page.md ─▶ LoadCorpus ─▶ chunkMarkdown: split on "#" lines (headings) ─▶ splitLong on blank lines (900 chars)
       └─▶ a "# comment" inside a fence looks like a heading ─▶ block split in two chunks
two chunks ─▶ embed (heading + text) ─▶ top K may contain only one half ─▶ half an answer
```

**Diagnosis steps.**
1. Log the retrieved chunk ids with every answer (my server logs only the count; this is a gap I would close first) and read the stored chunk text.
2. Print the chunks the splitter produced for that one document.
3. Look for a `#` line inside a code fence, and for a blank line inside a fence.
4. Check whether the second half would have been retrieved with a larger K, which shows whether it is a retrieval or a chunking problem.

**Fix now vs fix properly.**
- Now: raise K for this corpus, or hand-adjust the document so the script has no heading-like lines. Both are patches.
- Properly: a fence-aware splitter that never splits inside a fenced block, an overlap or parent-chunk strategy, and a golden corpus that includes code-heavy pages.

**How you'd test it.** A splitter test with a fenced block containing a `# comment` line and a blank line, asserting the block stays in one chunk. Extend the existing marker test (unique start and end markers per paragraph: a chunk with one marker but not the other proves a cut).

**Spoken answer (60-90 seconds).**
I would look at the stored chunks first, because chunking is the ceiling on retrieval quality and no index fixes incoherent chunks. My server logs the number of retrieved chunks but not their ids, so I would add the ids and read the chunk text for this request. I already know one limit of my splitter and I state it before anyone finds it: it treats any line starting with `#` as a heading, so a shell comment inside a code fence splits the block in two, and blank lines inside a fence are also split points. I accepted that for prose documentation, and it is not acceptable for a corpus full of scripts. The proper fix is a fence-aware splitter with a test that a fenced block with a comment and a blank line stays whole. I would also say my budget is 900 characters, not tokens, with no overlap, and I have not run a chunk-size sweep.

**Follow-ups the interviewer will ask.**
- *Why prepend the heading before embedding?* A section that says "run this command" is meaningless without the heading it sits under.
- *How did you prove the splitter never cuts a paragraph?* A test with unique markers per paragraph, and a check that nothing is dropped.
- *How do you pick a chunk size?* Judgment plus measurement. I have no golden retrieval set yet, so I have not validated 900.

**Tie to your code.** [L] [`fe-hands-on/server/corpus.go`](../../../../fe-hands-on/server/corpus.go) (`headingText`, `splitLong`), tests in [`fe-hands-on/server/corpus_test.go`](../../../../fe-hands-on/server/corpus_test.go).

---

## Scenario 5 🔴 Relevance collapses after a deploy, with no errors and flat latency

**Situation.** Tuesday 09:10 (example). The customer runs a persisted vector index (for example pgvector or a managed store) built by an ingest job. After a config change, the query service uses a different embedding model name than the ingest job. Retrieval returns results every time, thumbs-down rate doubles, and nothing logs an error.

**Level.** 🔴 Senior.

**What's being tested.** The one invariant between the write path and the read path: same embedding model. And how silent that failure is.

**Clarifying questions to ask first.**
1. Which embedding model built the stored vectors, and which does the query side use now? Is that recorded anywhere?
2. Same dimension or different dimension?
3. What changed in the last deploy, and was the ingest job or the query service changed?
4. Is there a golden retrieval set I can run against the live pair?
5. Is a rollback of the query-side config safe right now?

**Flow of control and data.**

```
WRITE: docs ─▶ chunk ─▶ embed (model A) ─▶ index
READ : query ─▶ embed (model B) ─▶ nearest neighbours in index ─▶ top K ─▶ prompt
        A != B: vectors live in different spaces; same dimension = silent garbage ranking
```

**Diagnosis steps.**
1. Compare the embedding model recorded on the index with the query service's config. If nothing is recorded, that is finding number one.
2. Look at the score distribution of the top results. Collapsing or near-equal scores point at a space mismatch.
3. Run the golden retrieval set and compare recall@K against the last known good.
4. Diff the last deploy's config for the embedding model variable.
5. Compare against an exact brute-force baseline on a sample of queries.

**Fix now vs fix properly.**
- Now: roll the query side back to the model that built the index. Cheap and fast.
- Properly: the model name and version are part of the index identity and are checked at startup, so a mismatch refuses to serve. Swap models by building a second versioned index beside the live one, backfilling, shadow-reading live queries, comparing offline, flipping the index and its query embedder together behind a flag, and keeping the old one warm for rollback.

**How you'd test it.** A startup test that fails when index metadata does not match the configured model. A golden retrieval set run on the live pair as a post-deploy check. A swap rehearsal test: build the new index, flip, assert the query embedder and index moved as one unit.

**Spoken answer (60-90 seconds).**
The key fact is that vectors from different models are not comparable, and nothing in the system warns you. So I would check what model built the index against what the query side uses, and look at score distributions and a golden retrieval set. My own code gets this right by construction inside one process: the in-memory retriever holds the embedder together with its chunks, so the pair always moves as one unit, and my dot product returns zero on a length mismatch so it cannot crash. But I should be honest about what that does not cover. Two different models with the same dimension are completely silent. Reading my retriever, it also returns the top K with no score threshold, so on an all-zero mismatch it would hand the prompt the first chunks by id order, not an error. That is my reading, not something I tested. The proper fix is the model name as part of the index identity, a versioned index built beside the live one, shadow reads, then an atomic flip with rollback. I have not run a persisted store or a live swap.

**Follow-ups the interviewer will ask.**
- *Cost of re-embedding?* The design document prices a full re-embed at about $0.12 per pass (March 2025 snapshot, verify current prices), so the real constraints are validation and rollback, not money.
- *Zero-downtime for the chat model?* Easier: a config value behind the `provider` interface, plus graceful shutdown so in-flight streams finish.
- *What breaks a rolling restart?* My server has graceful shutdown, but I have never run two instances behind a load balancer and my index is not persisted.

**Tie to your code.** [L] `memoryRetriever` pairing and `dot` in [`fe-hands-on/server/retriever.go`](../../../../fe-hands-on/server/retriever.go), config in [`fe-hands-on/server/config.go`](../../../../fe-hands-on/server/config.go), graceful shutdown in [`fe-hands-on/server/main.go`](../../../../fe-hands-on/server/main.go). [K] persisted store, versioned indexes and live swap (module 02 has an Illustrative `swappableRetriever`, scratch only).

---

## Scenario 6 🔴 The customer onboards 2 million chunks; p95 climbs and relevance quietly slips

**Situation.** Thursday 10:30 (example). A customer indexes their whole support archive, about 2 million chunks (example). Retrieval latency has gone from tens of milliseconds to seconds. After you move to an approximate index, latency is great, but a week later users say some obvious pages are never found.

**Level.** 🔴 Senior.

**What's being tested.** The recall x latency x cost triangle, brute force as an oracle, and how approximate search fails silently.

**Clarifying questions to ask first.**
1. How many vectors, how many dimensions, and what is the memory budget?
2. Which filters (tenant, product, date) apply, and are they applied before or after the nearest-neighbour step?
3. What recall is acceptable, and is there a measured baseline?
4. Single node or managed service, and where must the data live?
5. What is the p99 target?

**Flow of control and data.**

```
query ─▶ embed ─▶ ANN index (HNSW: ef_search trades recall for latency) ─▶ top K ─▶ prompt
sampled real queries (~1,000) ─▶ exact brute-force top K (offline oracle) ─▶ recall@K diff on a schedule
```

**Diagnosis steps.**
1. Read the retrieval time field in request logs (my server logs `retrieval_ms`) and plot p95/p99 against corpus size.
2. Estimate memory: vectors times dimensions times 4 bytes. For 10 million 1,536-dimensional vectors that is about 61 GB before any graph (derived arithmetic from my notes).
3. After switching to an ANN index, sample about 1,000 real queries, compute exact top K by brute force offline, and diff. That is the recall measurement.
4. Re-measure as the corpus grows at a fixed `ef_search`. Recall falls with growth, so a staging number says little about production.
5. Test with the real filters, because filtered ANN search is a separate failure mode.

**Fix now vs fix properly.**
- Now: cap K, add a warm cache for repeated queries, move to an approximate index with a safe `ef_search`.
- Properly: choose the operating model first (consistency, joins, data perimeter), tune the index second; scalar quantisation cuts memory about 4 times at a precision cost repaired by rescoring; schedule the recall check and alert when it drops.

**How you'd test it.** A recall regression test: the fixture of exact top K per sampled query, diffed against the live index. A load test with real filters at projected scale.

**Spoken answer (60-90 seconds).**
I would separate three things: latency, memory and recall. Brute force is exact, and its cost grows linearly with the number of vectors. In my lab a scratch benchmark with random 768-dimensional vectors on one laptop took about 14 ms at 10,000 vectors and about 165 ms at 100,000. Those are single numbers on random data, not a real-world claim, and I would not extrapolate them to millions. Past a certain size I would move to an approximate index, but then recall becomes the risk, because ANN search fails silently with normal latency and a full result set. So I would sample about a thousand real queries, compute the exact top K offline, and diff the index against it on a schedule. My in-memory retriever is exactly that oracle, which is a useful side effect of building it. I have run brute force only. HNSW, pgvector and a managed store are learning targets for me, so I would validate any choice with measured recall and p99 on the customer's data.

**Follow-ups the interviewer will ask.**
- *How do you choose between brute force, HNSW and a managed service?* Operating model first. A managed store removes index operations and adds a second system that every write must reach.
- *What would you not claim?* HNSW tuning experience, pgvector or Pinecone experience, or any measured recall of an approximate index.
- *Why was Couchbase chosen for Ask AI at 7,597 chunks?* My reading: the docs already live there and it does vector plus full-text in one query. The design document does not say so, and that scale would also have fit brute force.

**Tie to your code.** [L] brute-force scoring and stable sort in [`fe-hands-on/server/retriever.go`](../../../../fe-hands-on/server/retriever.go), `retrieval_ms` logging in [`fe-hands-on/server/stream.go`](../../../../fe-hands-on/server/stream.go), the Retriever seam. [K] HNSW, quantisation, managed stores. [P] Ask AI index and cost figures in the design document, a March 2025 snapshot.

---

## What not to claim in these scenarios

- I did not design or build Ask AI. I am a contributor and describe it from its design document.
- My build has no hybrid search, BM25, RRF, re-ranking, ANN index, pgvector or Pinecone. Those are [K] or Illustrative scratch code.
- The 14 ms and 165 ms figures are random vectors on one machine. Do not quote them as real-world.
- The refusal result is one 1B model, a 6-chunk corpus and two golden cases.
- My server has no authentication or rate limiting, no persisted index, and I have not run two instances behind a load balancer.
- The golden cases supply fixed context, so they test generation, not retrieval. No retrieval eval exists yet.
