# Module 02 in plain English: RAG and vector search

> **Read this first**
> - **What it is for:** learning how an AI answers from your own documents, from ingest to the final cited answer.
> - **Who it is for:** a beginner. Every term is explained the first time it appears.
> - **Full version:** [02-rag-and-vector-search.md](../02-rag-and-vector-search.md) (the senior module with code and numbers).

Lanes used in this file:
- **[P]** shipped at Couchbase. This is Ask AI. I am a contributor, it is 100% Couchbase's system, and I know it through a design document. I describe it and never quote its code.
- **[L]** my own build. A Go service in `fe-hands-on/server/` and an older Node prototype.
- **[K]** knowledge only. Hybrid search, RRF, re-ranking, ANN indexes, pgvector and Pinecone are not in my build.

Tags on numbers: **measured here** means I ran it while writing the module. **run 2026-09** means a logged run in my notes. **design-doc snapshot** means a figure from the Ask AI design document dated Mar 25, 2025. **derived** means arithmetic on those figures.

Code lives here:
- [fe-hands-on/server/](../../../../fe-hands-on/server/) (`main.go`, `stream.go`, `corpus.go`, `retriever.go`, `provider.go`, `config.go`)
- The older Node prototype is `RAG-app/server/couchbase.js`. It sits in a sibling folder outside this repo, at `/Users/aashishkumar/Documents/GitHub/RAG-app/`, so I do not link it.
- Design document: [Ask AI design document.md](../../../../docs/Ask%20AI%20design%20document.md)

---

## Phase 1 — Why RAG and how to frame the problem

**Analogy: an open-book exam.** A closed-book student guesses from memory, and guesses fluently. An open-book student looks up the right page first, then writes the answer. RAG is the open-book version for a model.

### Beginner points

**What is RAG, and why not ask the model directly?**
- RAG means retrieval-augmented generation. Before the model answers, my code searches our own documents.
- The best passages are put into the prompt (the text sent to the model).
- A model only knows its training data. On private or recent material it guesses, and the guess sounds confident.
- In my Agent Console, the server searches a Markdown corpus (a folder of documents) and gives the model only what it found.
- It also tells the model to decline when the corpus does not cover the question.
- A bonus: I can show the user the passages behind the answer, so they can check it.

### Intermediate points

**What is the control flow and data flow of one request?**
- The browser sends the whole conversation to `/api/chat` with a POST.
- `HandleChat` validates it and takes the last user message as the query.
- The retriever turns the query into a vector (a list of numbers that stands for meaning).
- It scores the query against every chunk vector and returns the top K chunks (K is just "how many").
- The handler writes a `sources` frame first. Then it builds the grounded prompt.
- Then it streams tokens from the provider (the thing that talks to the model).
- It finishes with a `done` frame carrying token counts and latency.
- Flow: browser -> HandleChat -> Retriever -> provider -> LLM -> browser (SSE events).
- SSE (server-sent events) means the server pushes small messages to the browser over one open connection.
- Three seams (places where one part can be swapped without touching the rest):
  - the `provider` interface: which LLM answers.
  - the `Retriever` interface: where vectors live.
  - the SSE event contract: what the browser relies on. It names neither the model nor the store.
- Advantage: a model swap, a store swap and a UI change are three independent edits.
- How I test it: stub versions of both interfaces, so the whole handler runs with no model and no network.
- The suite I re-ran had 46 passing cases in about 0.7 seconds, with 62.3% statement coverage (measured here).

### Senior points

**RAG, fine-tune, or long context?**
- RAG: for knowledge that is large, changing, and needs citations.
- Fine-tuning (training the model a bit more): for behaviour or format.
- Long context (pasting everything into the prompt): only when the whole corpus is small and static. Cost and latency grow with every token sent.
- My evidence is narrow but real.
  - Before retrieval, `llama3.2:1b` invented `CREATE VECTORS ON ...` three runs in a row for "how do I create a vector index?"
  - With retrieval plus an explicit permission to decline, it said "The provided documentation does not cover this."
- The limits are big: one 1B model, a 6-chunk corpus, two golden cases.
- I did not compare against fine-tuning or long context.
- At this size, pasting both Markdown files into the prompt would probably work too. I did not measure it.
- So I show the shape of the design, not that RAG beats the alternatives at this scale.
- One line in the prompt permits refusal. That line, not a bigger model, fixed the hallucination.

**When is RAG the wrong tool?**
- Exact lookups or sums, such as "status of ticket 4821" or "how many tickets closed last week". Those belong to a structured query.
- A tiny, static corpus. Brute-force search or plain long context is simpler and exact.
- Vector search answers "what is similar", not "what is exactly this" or "what is the total".

### Words you'll hear

| Term | One-line meaning |
|---|---|
| RAG | Search your documents first, then let the model answer from them. |
| Corpus | The set of documents you search. |
| Prompt | The text sent to the model. |
| Vector / embedding | A list of numbers that stands for the meaning of a text. |
| Top K | The K best-matching chunks. |
| Seam | A boundary where one part can be swapped out. |
| SSE | Server pushes small events to the browser over one connection. |
| Fine-tuning | Training a model a bit more on your data. |

**Say it in one breath:** RAG is an open-book exam for the model, and my build keeps the model, the store and the UI as three separate swappable seams.

---

## Phase 2 — Ingest and clean

**Analogy: a library intake desk.** Before a book goes on the shelf, staff remove the stickers and ads and file it under a clear label. If you skip that, the shelf fills with junk.

### Beginner points

**What does "ingest and clean" mean?**
- Ingest means getting raw documents into the system.
- Clean means removing what is not real content: navigation bars, footers, sidebars.
- It matters because search only finds what you stored.
- Junk that repeats on every page makes many chunks look alike.
- My Agent Console is simple: walk a directory and read every Markdown file.
- **[P]** In Ask AI, the source is HTML pages mirrored into an S3 bucket (cloud file storage). The weekly job strips headers, footers and sidebars before chunking. That is from the design document.

### Intermediate points

**What does my ingest do, and what does it guarantee?**
- `LoadCorpus` walks the directory recursively and keeps only files ending in `.md`.
- It reads each file and hands the text to the chunker.
- Read errors are wrapped and returned, not swallowed. A bad file cannot silently shrink the corpus.
- The document ID is the path relative to the corpus directory. Citations stay portable and do not leak an absolute path from my machine.
- A test makes a `.txt` file and a nested `.md` file. It checks that only Markdown is read, subdirectories are searched, and no document ID is absolute.
- The interesting line is the relative path, because the ID is what the citation later shows the user.

### Senior points

**How would I design ingest for production?**
- **[P]** In Ask AI, a weekly job in CP-Jobs fetches the HTML, cleans it, chunks it, embeds it and stores it.
- The design document says the synchronous run took about 5 to 6 hours, and about 20 minutes with 10 goroutines (lightweight parallel workers in Go). That is a design-doc snapshot, not measured by me.
- The same document lists an open problem: the S3 replication writes a new version of every object daily, so the bucket grows linearly.
- My own build re-embeds the whole corpus at every boot. It took 535 ms for 6 chunks (run 2026-09).
- That cost is linear in corpus size, nothing is persisted, and every replica would pay it.
- The failure I would design against: a half-finished re-embed that changes the live index in place. Part of the corpus is new and part stale, with no error.
- The safe pattern: build beside the live index, validate, then flip. I did not implement that.
- I have not built HTML boilerplate stripping at all, because my corpus is Markdown I wrote.
- A missing or empty corpus is survived loudly. Each branch logs a warning that answers will be ungrounded, and the console still runs.

**How would I ingest changes incrementally?**
- Store a content hash (a fingerprint of the text) per document.
- Re-chunk and re-embed only documents whose hash changed.
- Mark vectors from deleted documents for removal.
- **[P]** The design document prices a full re-embed at about $0.12 per pass for roughly 6 million tokens (design-doc snapshot). So I would justify incremental ingest by staleness and run time, not money.
- For a customer system like Jira or Zendesk, I would use webhooks plus a cursor-based backfill (that is module 05). I have not built that for RAG.

**An honest limit of my splitter.**
- A line starting with `#` inside a fenced code block is treated as a heading.
- That splits the code block in two.
- I accepted that for prose documentation. It would not be acceptable for a corpus full of shell scripts.
- I state it before they find it.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Ingest | Bring raw documents into the system. |
| Cleaning | Remove menus, footers and other non-content. |
| Document ID | The stable name a citation shows. |
| Content hash | A fingerprint used to detect a changed document. |
| Goroutine | A lightweight parallel worker in Go. |
| Backfill | Loading old data to catch up. |
| Fail loudly | Report the error instead of hiding it. |

**Say it in one breath:** Ingest turns raw files into clean, citable text, and mine is simple, re-embeds everything on boot, and has no HTML cleaning.

---

## Phase 3 — Chunk and embed

**Analogy: index cards.** If each card is too small, it has no context. If each card is too big, it talks about many things and matches none of them well. Chunking is cutting your notes into good cards.

### Beginner points

**What is a chunk, and what is an embedding?**
- A chunk is a small piece of a document that is searched and cited as one unit. An example is one section under a heading.
- An embedding is a list of numbers from a model. Similar meanings end up close together.
- To answer a question, I embed the question with the same model and find the nearest chunk vectors.
- Chunk size is the index-card trade-off above.

### Intermediate points

**How does my chunker work, and what do I embed?**
- I split on Markdown headings first. A heading is a topic break the author already declared.
- I split a section further only if it exceeds a soft budget of 900 characters.
- When I split, I add whole paragraphs until the budget is reached. I never cut a sentence in half.
- A code fence stays together unless it contains a blank line.
- I put the section heading in front of the chunk text before embedding. A section that says "run this command" means nothing without its heading.
- I normalize each vector once at index time (scale it to length one). Then query scoring is a plain dot product, which equals cosine similarity (an angle-based closeness score).
- Known edges I name first:
  - The budget is 900 characters, not tokens.
  - There is no overlap between chunks.
  - One paragraph longer than the budget stays whole, so the budget is soft.
  - Blank lines inside a code fence are also split points. The code comment overlooks this.

### Senior points

**How do I choose chunk size, prove the chunker, and what is the embedding invariant?**
- Chunking sets the ceiling on retrieval quality. A perfect index over incoherent chunks still retrieves the wrong thing.
- **[P]** Ask AI caps chunks at 1,000 tokens. It turned 2,667 documents into 7,597 chunks, about 2.8 chunks per document (design-doc snapshot, derived ratio).
- My 900-character budget is a judgment call I have not validated. I have no golden retrieval set yet.
- What I did prove is that the splitter is correct.
  - A test gives every paragraph a unique start and end marker.
  - A chunk holding one marker without the other proves a mid-paragraph cut.
  - The test also checks that nothing is dropped.
- The embedding invariant (a rule that must always hold): the write path and the read path use the same model.
  - Vectors from different models live in different spaces, and nothing warns you.
- My `dot` function returns zero when vector lengths differ, so a dimension mismatch cannot crash the server.
- But two different models with the same dimension would be silent. So I treat the model name as part of the index identity.
- That zero score is a deliberate fail-soft for the loud case. It does nothing for the silent case.

**Lesson from my Node prototype.**
- It embedded each whole document with no chunking, using `text-embedding-ada-002`.
- One vector blurred every topic on the page.
- The Go rewrite is where I took chunking seriously.

**How do I know the chunker is the problem when answers are bad?**
- I log retrieved chunk IDs with each answer and read the stored chunk text.
- If the answer is split across two chunks, or the chunk is an incoherent fragment, it is a chunking problem, not an index problem.
- My server logs how many chunks were retrieved, but not yet their IDs. I would close that gap first.
- I have not run a chunk-size sweep.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Chunk | A small unit of text that is searched and cited. |
| Embedding | The vector a model makes from a text. |
| Normalize | Scale a vector to length one. |
| Dot product | A simple multiplication-and-sum score for two vectors. |
| Cosine similarity | How close two vectors point in the same direction. |
| Overlap | Repeating a little text between neighbouring chunks. |
| Invariant | A rule that must always stay true. |

**Say it in one breath:** I cut text at headings, embed it with the heading attached, and always use one embedding model for both writing and reading.

---

## Phase 4 — Index and the vector-database choice

**Analogy: finding a book in a library.** Brute force means checking every book on every shelf. It is slow in a huge library but you never miss. An approximate index is a smart guide who gets you near the right shelf quickly, and sometimes misses.

### Beginner points

**What is a vector index, and do I always need a vector database?**
- A vector index is a structure that finds the nearest vectors without comparing against every one.
- Brute force compares the query to every vector. It is exact. It never misses the true nearest neighbours.
- HNSW (a graph-based fast search structure) is approximate. It is much faster on huge collections but can miss some true neighbours.
- I use brute force on purpose. With a handful of chunks, an approximate index adds tuning and risk and buys nothing.

### Intermediate points

**How does my search work, and where would a real vector store plug in?**
- `memoryRetriever` embeds the query, scores it against every chunk with a dot product, and sorts by score.
- It breaks ties by chunk ID, so results are stable and eval runs can be compared.
- Brute force has 100% recall (it finds every true match) by construction. It has no build step, no tuning knob, and no recall that can silently degrade.
- The `Retriever` interface is the seam. Couchbase, pgvector or Pinecone would implement `Retrieve(ctx, query, k)`, and nothing above changes.
- Pgvector is a Postgres extension for vectors. Pinecone is a managed vector service.
- Cost measured with a scratch benchmark of this loop: 768-dimension random vectors, one thread, full sort per query, on my laptop.
  - About 14 ms per query at 10,000 vectors.
  - About 165 ms at 100,000 vectors.
  - Random vectors, not real embeddings, and not committed to the repo (measured here).
- My README's 10,000-chunk rule of thumb is consistent with that. At that size, search takes tens of milliseconds next to a generation that takes seconds.

**What did it look like when the database did the scoring (Node prototype)?**
- The query went to Couchbase as SQL++ (Couchbase's SQL dialect) using `VECTOR_DISTANCE(embedding, $queryEmbedding, 'cosine')`, ordered ascending.
- The engine did the scoring. I never held vectors in app memory.
- The startup check for the vector index only logged a warning when it did not find one by name. So the prototype could run with no verified index behind the query.
- I am not certain of the exact ordering semantics of the cosine distance function. Verify it in the current Couchbase docs.
- Lesson: an unverified index is a performance and correctness unknown. I never measured recall on it.

### Senior points

**The recall x latency x cost triangle.**
- Brute force: exact recall. Latency grows linearly with the number of vectors. Cost is mostly memory for raw vectors.
- Memory is vectors times dimensions times four bytes. For 10 million 1,536-dimension vectors that is about 61 GB before any graph (derived arithmetic, from my vector-databases notes).
- HNSW trades recall for latency through `ef_search`, which can be changed live without a rebuild.
- `m` and `ef_construction` are build-time commitments.
- int8 quantization (storing numbers in fewer bits) cuts memory about 4 times at the price of precision. You repair that by rescoring.
- A managed service removes index operations. But it turns a storage choice into a distributed-systems one: every write must now land in two systems. It also moves your data outside your perimeter.
- I choose the operating model first, from consistency and join needs. I tune the index second.
- I would settle it with recall and p99 (the slowest 1% of requests) measured on my own data at projected scale, with real filters.
- Boundary: I have run brute force only. I have not run HNSW, pgvector or Pinecone. I have not measured recall of any approximate index. These are learning targets.
- **[P]** The Ask AI design document shows a Couchbase search index with a 1,536-dimension cosine vector field, marked "optimized for recall", over 7,597 chunks (design-doc snapshot).
  - That is below my 10,000-chunk threshold, so brute force would have been defensible on scale alone.
  - My reading, which the document does not state: the engine was chosen because the docs already live there and because it runs vector and full-text search in one query.

**How would I know an approximate index is silently losing recall?**
- Sample about 1,000 real queries.
- Compute the exact top K by brute force offline. Store that as a fixture.
- Diff the index against it on a schedule. Approximate search fails silently with normal latency and a full result set.
- My in-memory retriever is exactly that baseline oracle (a ground-truth reference).
- Recall also falls as the corpus grows at a fixed `ef_search`. A staging number says little about production.
- Recall is under-measured because latency pages you and recall does not.
- The recall@K metric is a small helper I wrote as an illustration, not in the repo.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Brute force | Compare the query to every vector; exact but linear. |
| ANN | Approximate nearest neighbour; fast but may miss some. |
| HNSW | A popular graph-based ANN index. |
| Recall | The share of true nearest neighbours that were found. |
| Quantization | Storing numbers in fewer bits to save memory. |
| p99 | The latency that 99% of requests beat. |
| SQL++ | Couchbase's SQL-like query language. |

**Say it in one breath:** I use exact brute-force search because my corpus is tiny, and I have never run an approximate index, so I treat recall measurement as a learning target.

---

## Phase 5 — Retrieve

**Analogy: two search clerks.** One clerk understands what you mean but is weak on exact codes. The other matches exact words but misses paraphrases. Asking both and merging their lists works better than trusting one.

### Beginner points

**Why is plain vector search not enough?**
- Vector search finds similar meaning. It handles a paraphrase like "how do I make my database faster" very well.
- It is weak on exact strings: an error code, a function name, a product SKU. They have little learned meaning and blur into neighbours.
- Keyword search, usually BM25 (a classic word-matching score), is the opposite. It matches exact words and misses paraphrases.
- Hybrid search runs both and merges the results.
- In my build I only made the vector half. My notes list BM25 as the next build.

### Intermediate points

**What is reciprocal rank fusion (RRF), and how would I add hybrid search?**
- RRF merges ranked lists by position, not by score.
- Each document gets the sum of 1 divided by (k plus its rank) across the lists. K is conventionally 60. Verify that for my data.
- I use ranks because cosine and BM25 scores are on different scales. They cannot be added meaningfully.
- Because `Retriever` is an interface, I would add a `hybridRetriever` that combines a dense retriever and a sparse retriever and returns the fused top K.
- Dense means vector search. Sparse means keyword search.
- I wrote this in a scratch copy. It compiled, and a small test passed showing a chunk both lists agree on rises to the top. It is not committed to the repo.
- It fails loudly if either retriever errors. That matches my rule: a retrieval failure must not quietly become a weaker answer.
- My existing retriever also has a stable tie-break, so results do not change between runs. A random order makes eval results impossible to compare.

### Senior points

**The right document is ranked 14th and never reaches the prompt. What do I do?**
- First, confirm it is a ranking problem and not a recall problem. Is the right chunk in the candidate pool at all? A re-ranker can only reorder what the retriever returned.
- If it is in the pool, retrieve wider (for example the top 20 to 100) and re-rank a short list down to K.
- Use a cheap heuristic first. Use a cross-encoder (a model that scores each question and chunk pair) only if measured quality justifies a model pass per candidate.
- **[P]** Ask AI does hybrid search in a single Couchbase query.
  - It falls back to pure vector search when hybrid returns nothing.
  - It applies a custom heuristic re-ranker that adds a length preference and content-type bonuses.
  - It passes the top 5 to the model. (Design-doc snapshot; I did not build or measure these parts.)
- In my own rig, the numbers say nothing about ranking quality. With 6 chunks and K=4, retrieval returned four of six chunks for both the answerable and the unanswerable question (run 2026-09).
- So no K sweep on that corpus is meaningful until I have a larger corpus and a golden retrieval set.
- I would ablate (remove one at a time to test) every heuristic bonus against that golden set. An unjustified bonus is tunable noise.

**Isn't Ask AI's silent fallback what I criticise in my prototype?**
- The two fallbacks differ in kind.
- **[P]** Ask AI falls back to pure vector search. That is still grounded retrieval. The design document says it logs which search type was used, so the degradation is visible.
- My prototype fell back to a `LIKE '%query%'` text search and reported a constant similarity of 1.0. That hides the failure behind a fake score.
- My principle: a fallback is fine if it stays grounded and is observable. It is not fine if it pretends nothing happened.
- I fixed this in the rewrite by making retrieval failure an error frame (see Phase 6).

### Words you'll hear

| Term | One-line meaning |
|---|---|
| BM25 | A classic keyword-matching score. |
| Dense / sparse | Vector search / keyword search. |
| Hybrid search | Run both and merge. |
| RRF | Merge ranked lists by position, using 1/(k+rank). |
| Re-ranker | A second step that reorders a short candidate list. |
| Cross-encoder | A model that scores a question and chunk pair together. |
| Ablate | Remove one part to see what it really adds. |
| Fallback | A backup path used when the first fails. |

**Say it in one breath:** Vector search misses exact strings and keyword search misses paraphrases, so I would fuse both by rank, and I have only built the vector half.

---

## Phase 6 — Ground and generate

**Analogy: a witness under oath.** The witness may only say what is in the evidence on the table. "I do not know" is an allowed answer, and they must point to which exhibit they used.

### Beginner points

**What does "grounding" mean, and how does the model know it may say "I don't know"?**
- Grounding means the answer must come from the retrieved passages, not the model's memory.
- The model knows it may decline only because the system prompt says so in plain words.
- Without that permission, models tend to fill gaps with confident invention.
- My prompt says three things: answer using only the context, reply with a fixed sentence when the context lacks the answer, and cite sources by number.

### Intermediate points

**How is the prompt assembled, and how do citations work?**
- `buildMessages` numbers each retrieved chunk as `[1]`, `[2]` and so on, with its title and document ID.
- It puts that text into a server-owned system prompt, then adds the conversation.
- The prompt tells the model to cite by those numbers.
- The same chunks go to the browser in a `sources` frame, so the UI can match a citation to its evidence.
- The server rejects any client-supplied `system` message. Accepting one would let a web page overwrite the grounding rules.
- If there are no chunks, the code uses a separate, honest "no corpus configured" prompt instead of pretending to be grounded.
- There are exactly two prompts, and the server owns both.
- Citations are requested by the prompt. I do not verify that a cited number exists.

**In what order do things happen on the wire?**
- Retrieve first. Write a `sources` frame before any token. Stream tokens. End with a `done` frame carrying usage.
- Sources first lets the UI show evidence while the answer is still being written. It also shows citations come from the same chunks that went into the prompt.
- If retrieval fails, the handler sends one `error` frame and returns without calling the model.
- A test asserts the provider is never called in that case. Answering ungrounded without saying so is the dangerous path.
- The handler comment and the test name both say this, so the rule is enforced and not just stated.

### Senior points

**Refusal, citations and streaming, and what can still go wrong.**
- Refusal is a prompt contract, not a retrieval gate.
  - For both answerable and unanswerable questions, retrieval returned four chunks.
  - So the model declined because I permitted it, not because retrieval found nothing.
- Measured effect: the refusal used 9 completion tokens in both logged runs. The answerable question used 162 tokens in one run and 128 in another.
- So I say "roughly 14 to 18 times fewer output tokens" and I do not quote a precise ratio. These are single samples, `llama3.2:1b`, CPU only (run 2026-09).
- Streaming gives perceived speed but needs failure handling.
  - If the client disconnects, the handler logs and stops. It does not try to write an error frame.
  - Cancelling the request context aborts the upstream generation, so I do not pay for tokens nobody reads.
- What can still go wrong:
  - An empty retrieval result silently selects the ungrounded prompt. If I add a similarity-score threshold, I must change that branch.
  - Retrieved text goes into the system prompt without delimiting or sanitising. That is fine for first-party docs. It is not fine for untrusted content like customer tickets.
  - A model-written `[3]` is never checked against the sources list.
- Boundary: I validated refusal on two golden cases with a 1B model, not on a broad adversarial set.

**How would I stop a fabricated citation or prompt injection from retrieved content?**
- Citations: parse the `[n]` markers from the finished answer. Check that each n is within the number of sources. Emit a warning event or fail an eval if not.
- Injection: wrap each chunk in clearly labelled blocks. Tell the model the contents are data, not instructions. Keep tools and secrets out of reach of that prompt.
- Measure with an injection test set. Do not trust the wrapping alone. A delimiter is a mitigation, not a guarantee.
- Neither check is built in my repo today.
- The client-side half is built: the server refuses a `system` role from the browser. The retrieved-content half is the gap above.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Grounding | Answers come only from the retrieved passages. |
| System prompt | The server's standing instructions to the model. |
| Citation | A pointer like [2] to the source used. |
| Frame | One SSE message: `sources`, `token`, `done` or `error`. |
| Prompt injection | Text in data that tries to give the model new orders. |
| Parametric memory | What the model remembers from training. |
| Delimiter | A marker that separates data from instructions. |

**Say it in one breath:** The server builds the prompt, shows sources first, refuses loudly when retrieval fails, and lets the model say "I do not know" only because the prompt allows it.

---

## Phase 7 — Cost, scale and swapping models without downtime

**Analogy: a restaurant's costs.** The big bill is the chef (the big model) who cooks each order. Buying ingredients (embeddings) is cheap. The rent (the database cluster) is fixed whether you serve one customer or a hundred.

### Beginner points

**Where does the money go?**
- Almost all of it goes to the large language model that writes the answer. You pay per token for both prompt and reply.
- Embedding is very cheap, so re-embedding the whole document set is a rounding error.
- The database cluster is a fixed monthly cost.
- **[P]** In the Ask AI design document, model calls were about $0.0173 per request. The cluster was a fixed $208.80 per month. This is a design-doc snapshot. Prices will have moved, so verify in current docs.

### Intermediate points

**How do I swap the chat model and the embedding model?**
- The chat model is a config value behind the `provider` interface. Changing `OLLAMA_MODEL` and restarting is the whole change.
- I verified a swap to `qwen2.5:1.5b` with no code change (run 2026-09).
- The embedding model is different because it is stateful. `EMBED_MODEL` must match the model that indexed the corpus.
- My retriever holds the embedder together with the chunks. So a freshly built retriever carries its own query embedder, and the pair moves as one unit.
- My server does not do a live swap. It re-embeds at boot, so a swap means a restart.
- I would promote a new fully built index in one atomic step (one indivisible switch). The snippet that does this compiled and passed a small test in a scratch copy.
- In production I would add a validation step on a golden set before promoting.

### Senior points

**Zero-downtime embedding swap, and cost and scale.**
- A new embedding model is a new vector space. I never update in place.
- The steps:
  - Build a second, versioned index beside the live one.
  - Backfill it.
  - Shadow-read live queries against it without serving them.
  - Compare quality offline.
  - Flip behind a flag.
  - Keep the old index warm for rollback.
- The cost is not embedding calls. A full re-embed was about $0.12 per pass in the design document (design-doc snapshot). The real constraints are validation and rollback.
- The chat-model swap is easier. My server already supports a rolling restart: it stops accepting connections on SIGTERM (the "please stop" signal) and gives in-flight streams a grace period to finish.
- That graceful shutdown is a necessary condition for zero downtime, not the whole story.
- From the document's own per-call figures I derive about $0.01732 per request.
- The crossover is near 12,000 requests per month. Below it the fixed cluster dominates. Above it token spend does (derived; verify current prices).
- The rephrasing call is about a third of that model spend (derived).
- The document's printed rephrasing figure of $589.25 per million requests looks like a typo for $5,892.50 by its own arithmetic. I would confirm with the source spreadsheet.
- Boundary: I have never run two instances behind a load balancer. My index is not persisted. I do not extrapolate my 535 ms boot embed to a large corpus.

**How would I cut cost by half?**
- In order of leverage:
  - Add a semantic cache for repeated questions. The design document lists it as a future improvement.
  - Shrink the rephrasing call: a smaller model and fewer history turns than the current five.
  - Tighten K and the prompt.
  - Only then look at the generation model.
- Each change goes through the golden set first. Quality is measured, not assumed.
- **[P]** The design document describes per-tenant limits on calls per minute, requests per day and tokens per month, with free and paid tiers (design-doc snapshot).
- My own server has no authentication or rate limiting. Its README says so.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Token cost | You pay per token read and written by the model. |
| Fixed cost | Money paid regardless of traffic, like a cluster. |
| Shadow read | Run a new path on real queries without serving its result. |
| Rollback | Return to the previous working version. |
| SIGTERM | The signal asking a program to shut down. |
| Semantic cache | Reuse an answer for a similar earlier question. |
| Rate limit | A cap on how many calls are allowed. |

**Say it in one breath:** The model is the big cost, a chat-model swap is a config change, and an embedding swap needs a new index built beside the old one.

---

## Mix-ups to avoid

- **Refusal is not retrieval.** The model declined because the prompt allowed it. Retrieval still returned four chunks.
- **Brute force is not "bad".** It is exact, simple and right at small scale. It just grows linearly.
- **Recall is not latency.** Latency pages you when it is slow. Recall can fall silently.
- **Hybrid and re-ranking are not in my build.** They are Ask AI **[P]** design-doc items or my scratch sketch.
- **The same embedding model must write and read.** Mixing models gives silent, wrong results.
- **A fallback must stay grounded and visible.** A fake similarity of 1.0 is the opposite.

---

## What I built vs what I only know

**Built, my own [L]:**
- A Go service: Markdown corpus, heading-aware chunker, in-memory brute-force retriever, grounded prompt, SSE streaming.
- A stub-based test suite. The 46 cases and 62.3% coverage are measured here.
- Refusal tested on one 1B model, a 6-chunk corpus and two golden cases. Token counts are single samples (162 vs 128 varied between runs).
- Retrieval is not evaluated. The golden cases supply fixed context, so they test generation, not retrieval.
- An older Node prototype with no chunking and a silent text fallback.
- The 14 ms and 165 ms numbers are random 768-dimension vectors on one machine with a full sort. Do not quote them as real-world.
- My server has no zero-downtime swap, no persistence, no authentication and no rate limiting. The README lists these as known limits.

**Shipped at Couchbase [P]:**
- Ask AI. I am a contributor. I did not design or build it alone.
- Hybrid search, the heuristic re-ranker, K=5 and the weekly job are described in a design document written by others. Be ready to say exactly which parts I touched. These documents do not record that.
- Costs and prices are a March 2025 snapshot. The $5,892.50 correction is my own derivation.
- Do not quote any code from the couchbase-cloud monorepo.

**Knowledge only [K]:**
- HNSW tuning, pgvector, Pinecone, hybrid search, BM25, RRF and re-ranking. These are learning targets. No measured recall of any approximate index.
- Say "verify in current docs" for external facts such as pgvector 0.8.0 iterative scans, Couchbase 8.0 index types, RRF k=60 as a default, and current model names.
