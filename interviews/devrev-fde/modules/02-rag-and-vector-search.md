# Module 02 — RAG & vector search

> This module covers retrieval-augmented generation end to end: framing the problem, ingest, chunking and embedding, the index and vector-database choice, retrieval, grounded generation, and cost and model swaps. The code I built myself **[L]** lives in `AI/fe-hands-on/server/` (a Go service: Markdown corpus, heading-aware chunker, in-memory brute-force retriever, grounded prompt, SSE streaming) and in an older Node prototype at `RAG-app/server/couchbase.js`. What shipped at Couchbase **[P]** is Ask AI; I am marked a contributor on it, it is 100% Couchbase's system, and I know it through `AI/docs/Ask AI design document.md`, so I describe it and never quote its code. Hybrid search, RRF, re-ranking, ANN indexes, pgvector and Pinecone are **not** in my build: where this guide shows them, the code is labelled Illustrative and the experience is a learning target, not a claim.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Why RAG and how to frame the problem | Decide RAG vs fine-tune vs long context, and draw the request flow and the seams | `server/main.go`, `server/stream.go` |
| 2. Ingest and clean | Turn raw documents into clean text with a stable, citable identity | `server/corpus.go` (`LoadCorpus`) |
| 3. Chunk and embed | Cut text into retrievable units and map each to a vector with one model | `server/corpus.go`, `server/retriever.go` |
| 4. Index and the vector-database choice | Pick brute force, HNSW or a managed store by the recall x latency x cost triangle | `server/retriever.go` (`memoryRetriever`) |
| 5. Retrieve | Get the right candidates: dense, sparse, fusion, re-ranking, K | `server/retriever.go`, Illustrative hybrid |
| 6. Ground and generate | Build the prompt, permit refusal, cite, stream, and fail loudly | `server/stream.go`, `server/provider.go` |
| 7. Cost, scale and swapping models without downtime | Know where money goes and swap generation and embedding models safely | `server/config.go`, `server/main.go`, Ask AI design doc |

Paths in this guide are relative to `/Users/aashishkumar/Documents/GitHub/`, and `server/` means `AI/fe-hands-on/server/`. Number origins are tagged: **(measured here)** means I ran it while writing this guide, **(run 2026-09)** means a logged run in `AI/docs/notes/`, **(design-doc snapshot)** means a figure from the Ask AI design document dated Mar 25, 2025, and **(derived)** means arithmetic on those figures.

---

## Phase 1 — Why RAG and how to frame the problem

### 🟢 Beginner

**Q:** What is RAG, and why not just ask the model directly?

**A:** RAG stands for retrieval-augmented generation. I explain it as an open-book exam instead of a closed-book one: before the model answers, my code searches our own documents and puts the most relevant passages into the prompt. A model only knows its training data, so on private or recent material it guesses, and it guesses fluently. In my Agent Console the server searches a Markdown corpus, hands the model only what it found, and tells it to decline when the corpus does not cover the question. As a side benefit I can show the user the passages the answer was built from, so they can check it.

### 🟡 Intermediate

**Q:** Walk me through the control flow and data flow of a request in your RAG service, and tell me how you test it.

**A:** The browser POSTs the whole conversation to `/api/chat`, and `HandleChat` validates it and takes the last user message as the query. The retriever embeds that query, scores it against every chunk vector, and returns the top K chunks. The handler then writes a `sources` frame first, builds the grounded prompt, streams tokens from the provider, and finishes with a `done` frame that carries token counts and latency. I isolate change behind three seams: the `provider` interface for which LLM answers, the `Retriever` interface for where vectors live, and the SSE event contract so the UI names neither the model nor the store. I test it with stub implementations of both interfaces, so the whole handler runs with no model and no network; I re-ran the suite for this guide and got 46 passing cases in about 0.7 seconds with 62.3% statement coverage **(measured here)**.

**Source:** `AI/fe-hands-on/server/main.go:3-13`
```go
// ARCHITECTURE
//
//	browser ──POST /api/chat──▶ HandleChat ──▶ Retriever ──▶ embeddings + corpus
//	        ◀── SSE: {sources} {token}* {done} ──┘         └─▶ provider ──▶ LLM
//
// Three seams, each isolating one kind of change:
//
//   - `provider`  — which LLM answers. Ollama today, Bedrock later.
//   - `Retriever` — where vectors live. In-memory today, Couchbase/pgvector later.
//   - the SSE event contract — what the browser codes against. It names neither
//     the model nor the store, so both can be replaced without touching the UI.
```

How to talk about it: I draw this arrow diagram on the whiteboard and point at the three seams, because that is the architecture answer. The advantage is that a model swap, a store swap and a UI change are three independent edits.

### 🔴 Senior

**Q:** A customer asks whether they should do RAG, fine-tune, or just use a long context window. How do you frame it, and what evidence do you have?

**A:** I frame it by what kind of problem it is: RAG for knowledge that is large, changing and needs citations, fine-tuning for behavior or format, and long context only when the whole corpus is small and static, because cost and latency grow with every token you send. The evidence from my own build is narrow but real: before retrieval, `llama3.2:1b` answered "how do I create a vector index?" by inventing `CREATE VECTORS ON ...` three runs in a row, and with retrieval plus an explicit instruction that it may decline, the same model answered "The provided documentation does not cover this." The boundary of that claim is large: one 1B model, a 6-chunk corpus, two golden cases, and I did not compare against fine-tuning or long context. At that corpus size, stuffing both Markdown files into the prompt would probably also work, though I did not measure the full-corpus prompt, so what I am demonstrating is the shape of the design rather than that RAG beats the alternatives at this scale.

**Source:** `AI/fe-hands-on/server/stream.go:81-95`
```go
// groundedSystemPrompt is the instruction wrapped around retrieved context.
//
// The explicit permission to say "I don't know" is the load-bearing line: a
// model with no such instruction fills gaps with fluent invention, which is
// precisely the failure the eval suite's negative case exists to catch.
const groundedSystemPrompt = `You are a documentation assistant. Answer using ONLY the context below.

Rules:
- If the context does not contain the answer, reply exactly: "The provided documentation does not cover this."
- Never invent syntax, commands, parameters, or steps that do not appear in the context.
- Cite the sources you used by their [n] number.
- Be concise and give actionable steps.

Context:
%s`
```

How to talk about it: I point at the single line that permits refusal and say that this, not a bigger model, fixed the hallucination.

**Follow-up they will ask:** When would you tell the customer RAG is the wrong tool?

**A:** I would say so when the question is really an exact lookup or an aggregation, such as "what is the status of ticket 4821" or "how many tickets closed last week", because those belong to a structured query and not to similarity search. I would also say so when the corpus is tiny and static, since brute-force search or plain long context is simpler and exact. My vector-databases notes make the same point: vector search answers "what is similar", not "what is exactly this" or "what is the total".

---

## Phase 2 — Ingest and clean

### 🟢 Beginner

**Q:** What does "ingest and clean" mean, and why does it matter before any AI happens?

**A:** Ingest means getting the raw documents into the system, and clean means removing everything that is not real content, such as navigation bars, footers and sidebars. It matters because the search can only find what you stored, and junk that repeats on every page makes many chunks look alike. In my Agent Console, ingest is deliberately simple: walk a directory and read every Markdown file. In Ask AI, the source is HTML pages mirrored into an S3 bucket, and the weekly job strips headers, footers and sidebars before chunking, according to the design document.

### 🟡 Intermediate

**Q:** Show me how your ingest works and what it guarantees.

**A:** `LoadCorpus` walks the directory recursively, keeps only files ending in `.md`, reads each file, and hands the text to the chunker. Read errors are wrapped and returned instead of swallowed, so a bad file cannot silently shrink the corpus. The document ID is the path relative to the corpus directory, which keeps citations portable instead of leaking an absolute path from my machine. A test covers exactly that: it creates a `.txt` file and a nested `.md` file, then checks that only Markdown is read, that subdirectories are recursed, and that no document ID is absolute.

**Source:** `AI/fe-hands-on/server/corpus.go:34-62`
```go
func LoadCorpus(dir string) ([]Chunk, error) {
	var chunks []Chunk

	err := filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !strings.HasSuffix(strings.ToLower(d.Name()), ".md") {
			return nil
		}

		content, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read %s: %w", path, err)
		}

		rel, err := filepath.Rel(dir, path)
		if err != nil {
			rel = path
		}

		chunks = append(chunks, chunkMarkdown(rel, string(content))...)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return chunks, nil
}
```

**Source:** `AI/fe-hands-on/server/corpus_test.go:121-142`
```go
func TestLoadCorpusReadsOnlyMarkdown(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "a.md"), []byte("# A\n\nalpha"), 0o644)
	os.WriteFile(filepath.Join(dir, "b.txt"), []byte("ignored"), 0o644)
	os.MkdirAll(filepath.Join(dir, "nested"), 0o755)
	os.WriteFile(filepath.Join(dir, "nested", "c.md"), []byte("# C\n\ngamma"), 0o644)

	chunks, err := LoadCorpus(dir)
	if err != nil {
		t.Fatalf("LoadCorpus: %v", err)
	}
	if len(chunks) != 2 {
		t.Fatalf("got %d chunks, want 2 (.md only, recursing into subdirs): %+v", len(chunks), chunks)
	}

	// DocIDs must be relative so citations are portable, not machine-specific.
	for _, c := range chunks {
		if filepath.IsAbs(c.DocID) {
			t.Errorf("docID %q is absolute; citations would leak local paths", c.DocID)
		}
	}
}
```

How to talk about it: I say that the interesting line is the relative path, because the ID is what the citation will later show the user.

### 🔴 Senior

**Q:** Design ingest for production: freshness, cost, and what breaks.

**A:** In Ask AI a weekly job in CP-Jobs fetches the HTML, cleans it, chunks it, embeds it and stores it, and the design document says the synchronous run took about 5 to 6 hours and about 20 minutes with 10 goroutines **(design-doc snapshot, not measured by me)**. The same document lists an open storage problem: the S3 replication writes a new version of every object daily, so the bucket grows linearly. My own build re-embeds the whole corpus at every boot, which took 535 ms for 6 chunks **(run 2026-09)**, but that is linear in corpus size, nothing is persisted, and every replica would pay it. The failure I would design against is a half-finished re-embed that mutates the live index in place, which leaves part of the corpus new and part stale with no error; the safe pattern is to build beside the live index, validate, then flip. I did not implement that in my repo, and I have not built HTML boilerplate stripping at all, because my corpus is Markdown that I wrote.

**Source:** `AI/fe-hands-on/server/main.go:130-140`
```go
	chunks, err := LoadCorpus(cfg.CorpusDir)
	if err != nil {
		// A missing corpus directory is a configuration mistake worth surviving:
		// the console still runs, loudly ungrounded, rather than refusing to boot.
		log.Warn("corpus unavailable: answers will be ungrounded", "dir", cfg.CorpusDir, "err", err)
		return srv, nil
	}
	if len(chunks) == 0 {
		log.Warn("corpus is empty: answers will be ungrounded", "dir", cfg.CorpusDir)
		return srv, nil
	}
```

How to talk about it: this block shows that a missing or empty corpus is survived loudly and not silently, since each branch logs a warning that answers will be ungrounded.

**Follow-up they will ask:** How would you ingest changes incrementally instead of re-embedding everything?

**A:** I would store a content hash per document, re-chunk and re-embed only documents whose hash changed, and mark vectors from deleted documents for removal. The design document prices a full re-embed at about $0.12 per pass for roughly 6 million tokens **(design-doc snapshot)**, so I would justify incremental ingest by staleness and run time rather than by money. For a customer system such as Jira or Zendesk I would drive it from webhooks plus a cursor-based backfill, which is module 05, and I have not built that for RAG specifically.

One honest limitation of my splitter shows up at ingest time, and I state it before they find it:

**Source:** `AI/fe-hands-on/server/corpus.go:101-115`
```go
// headingText reports whether a line is an ATX Markdown heading and returns its
// text. Fenced code can contain lines starting with '#', but treating those as
// headings only ever splits a code block into two retrievable pieces, which is
// an acceptable failure for a corpus of prose documentation.
func headingText(line string) (string, bool) {
	trimmed := strings.TrimSpace(line)
	if !strings.HasPrefix(trimmed, "#") {
		return "", false
	}
	text := strings.TrimSpace(strings.TrimLeft(trimmed, "#"))
	if text == "" {
		return "", false
	}
	return text, true
}
```

How to talk about it: the comment says a `#` line inside a fenced code block is treated as a heading and splits the code block in two; I accepted that for prose documentation, and it would not be acceptable for a corpus full of shell scripts.

---

## Phase 3 — Chunk and embed

### 🟢 Beginner

**Q:** What is a chunk, and what is an embedding?

**A:** A chunk is a small piece of a document that is searched and cited as one unit, such as one section under a heading. An embedding is a list of numbers, a vector, that a model produces from a piece of text so that texts with similar meaning end up close together. To answer a question, I turn the question into a vector with the same model and find the chunks whose vectors are nearest. I think about chunk size like index cards: too small and a card has no context, too large and a card talks about many things and matches none of them sharply.

### 🟡 Intermediate

**Q:** How does your chunker work, and what exactly do you embed?

**A:** I split on Markdown headings first, because a heading is a topic break the author already declared, and I only split a section further when it exceeds a soft budget of 900 characters. When I do split, I accumulate whole paragraphs until the budget is reached, so I never cut a sentence in half, and a code fence stays together unless it contains a blank line. When I embed, I prepend the section heading to the chunk text, because a section that just says "run this command" is meaningless without the heading it sits under. I normalize each vector once at index time, so scoring at query time is a plain dot product that equals cosine similarity.

**Source:** `AI/fe-hands-on/server/corpus.go:120-143`
```go
func splitLong(text string) []string {
	if len(text) <= chunkTarget {
		return []string{text}
	}

	var (
		parts   []string
		current []string
		size    int
	)

	for _, para := range strings.Split(text, "\n\n") {
		if size > 0 && size+len(para) > chunkTarget {
			parts = append(parts, strings.Join(current, "\n\n"))
			current, size = nil, 0
		}
		current = append(current, para)
		size += len(para)
	}
	if len(current) > 0 {
		parts = append(parts, strings.Join(current, "\n\n"))
	}
	return parts
}
```

**Source:** `AI/fe-hands-on/server/retriever.go:105-111`
```go
	texts := make([]string, len(chunks))
	for i, c := range chunks {
		// Prepending the heading gives the embedding topical context the chunk
		// body may not restate — a section that says "run this command" is
		// meaningless without the heading it sits under.
		texts[i] = c.Title + "\n\n" + c.Text
	}
```

**Source:** `AI/fe-hands-on/server/retriever.go:118-124`
```go
	indexed := make([]Chunk, len(chunks))
	for i := range chunks {
		indexed[i] = chunks[i]
		// Normalize once at index time so query-time scoring is a plain dot
		// product: cosine similarity without repeating the division per query.
		indexed[i].Vector = normalize(vectors[i])
	}
```

How to talk about it: I mention that the budget is 900 characters and not tokens, that there is no overlap, that a single paragraph longer than the budget stays whole, so the budget is soft, and that blank lines inside a code fence are also split points, which the code comment overlooks. Those are the known edges, and naming them first is what makes the design look intentional.

### 🔴 Senior

**Q:** How do you choose chunk size, how do you prove the chunker is right, and what is the one invariant on the embedding side?

**A:** Chunking sets the ceiling on retrieval quality, because a perfect index over incoherent chunks reliably retrieves the wrong thing. Ask AI caps chunks at 1,000 tokens and turned 2,667 documents into 7,597 chunks, which is about 2.8 chunks per document **(design-doc snapshot, derived ratio)**, and my 900-character budget is a judgment call that I have not validated, because I have no golden retrieval set yet. What I did prove is correctness of the splitter: a test gives every paragraph a unique start and end marker, so any chunk holding one marker without the other proves a mid-paragraph cut, and the test also checks that nothing is dropped. On the embedding side the invariant is that the write path and the read path must use the same model, since vectors from different models live in different spaces and nothing in the system warns you. My `dot` function returns zero for mismatched lengths so a dimension mismatch cannot crash the server, but two different models with the same dimensionality would be completely silent, which is why I treat the model name as part of the index identity.

**Source:** `AI/fe-hands-on/server/retriever.go:190-203`
```go
// dot returns the dot product, which equals cosine similarity for unit vectors.
// Mismatched lengths score 0 rather than panicking: that only happens if two
// different embedding models were used, and a zero score keeps the chunk out of
// the results instead of taking the server down.
func dot(a, b []float32) float64 {
	if len(a) != len(b) {
		return 0
	}
	var sum float64
	for i := range a {
		sum += float64(a[i]) * float64(b[i])
	}
	return sum
}
```

How to talk about it: the zero-score is a deliberate fail-soft for the loud case, and I say plainly that it does nothing for the silent case.

My earlier Node prototype shows the opposite approach, which is worth saying out loud as a lesson learned:

**Source:** `RAG-app/server/couchbase.js:92-94`
```javascript
    // Generate embedding for the content
    const content = document.content || document.text || '';
    const embedding = await generateEmbedding(content);
```

How to talk about it: that prototype embedded each whole document with no chunking and used `text-embedding-ada-002` (line 77), so one vector blurred every topic on the page; the Go rewrite is where I took chunking seriously.

**Follow-up they will ask:** How do you know the chunker is the problem when answers are bad?

**A:** I log the retrieved chunk IDs with every answer and read the stored chunk text. If the answer is split across two chunks, or the retrieved chunk is an incoherent fragment, it is a chunking problem, not an index problem. My server logs how many chunks were retrieved but not yet their IDs, which is a gap I would close first, and I have not run a chunk-size sweep.

---

## Phase 4 — Index and the vector-database choice

### 🟢 Beginner

**Q:** What is a vector index, and do I always need a vector database?

**A:** A vector index is a data structure that finds the nearest vectors to a query without comparing against every single one. The simplest approach, called brute force, compares the query to every vector, and it is exact, so it never misses the true nearest neighbours. The faster approaches, such as HNSW, are approximate: they are much faster on huge collections but may miss some true neighbours. In my Agent Console I use brute force on purpose, because with a handful of chunks an approximate index adds tuning and risk and buys nothing.

### 🟡 Intermediate

**Q:** Show me your search, justify brute force, and tell me where a real vector store would plug in.

**A:** My `memoryRetriever` embeds the query, scores it against every chunk with a dot product, sorts by score, and breaks ties by chunk ID so results are stable and eval runs are diffable. Brute force is 100% recall by construction, with no build step, no tuning knob and no recall that can silently degrade. The `Retriever` interface is the seam: Couchbase, pgvector or Pinecone would implement `Retrieve(ctx, query, k)` and nothing above that line changes. I measured the cost of the approach with a scratch benchmark that mirrors this loop: 768-dimensional random vectors, one thread, a full sort per query, on this laptop, gave about 14 ms per query at 10,000 vectors and about 165 ms at 100,000 **(measured here; random vectors, not real embeddings, not committed to the repo)**.

**Source:** `AI/fe-hands-on/server/retriever.go:13-19`
```go
// Retriever finds the chunks most relevant to a query. It is an interface for
// the same reason `provider` is: the store is a swap seam. An in-memory brute
// force store today, Couchbase or pgvector later, with nothing above this line
// needing to change.
type Retriever interface {
	Retrieve(ctx context.Context, query string, k int) ([]Chunk, error)
}
```

**Source:** `AI/fe-hands-on/server/retriever.go:142-150`
```go
	type scored struct {
		chunk Chunk
		score float64
	}

	ranked := make([]scored, 0, len(r.chunks))
	for _, c := range r.chunks {
		ranked = append(ranked, scored{chunk: c, score: dot(q, c.Vector)})
	}
```

How to talk about it: I say that the 10,000-chunk rule of thumb in my README is consistent with that measurement, because at that size the search is tens of milliseconds next to a generation that takes seconds, and I flag that the numbers come from random vectors on one machine.

**Q:** What did it look like when the database did the scoring, in your earlier prototype?

**A:** In the Node prototype the query went to Couchbase as SQL++ with `VECTOR_DISTANCE(embedding, $queryEmbedding, 'cosine')`, ordered ascending, so the engine did the scoring and I never held vectors in application memory. The startup check for the vector index only logs a warning when it does not find one by name, so the prototype could run with no verified index behind the query. I am not certain of the exact ordering semantics of the cosine distance function, so I would verify that in the current Couchbase docs before relying on it.

**Source:** `RAG-app/server/couchbase.js:127-133`
```javascript
    const searchQuery = `
      SELECT 
        META().id as doc_id,
        content,
        text,
        metadata,
        VECTOR_DISTANCE(embedding, $queryEmbedding, 'cosine') as similarity
```

**Source:** `RAG-app/server/couchbase.js:57-66`
```javascript
    const vectorIndexExists = indexes.some(index => 
      index.name === 'vector_search_index' || 
      index.indexKey.includes('vector')
    );

    if (!vectorIndexExists) {
      console.log('⚠️  Vector search index not found. You need to create it manually in Couchbase UI.');
      console.log('📖 Follow the guide: https://www.couchbase.com/blog/guide-to-data-prep-for-rag/');
    } else {
      console.log('✅ Vector search index found');
```

How to talk about it: the lesson I took is that a retrieval path with an unverified index is a performance and correctness unknown, and that I never measured recall on it.

### 🔴 Senior

**Q:** Explain the recall x latency x cost triangle and how you would choose between brute force, HNSW and a managed service.

**A:** Brute force gives exact recall, its latency grows linearly with the number of vectors, and its cost is mostly the memory to hold raw vectors, which is vectors times dimensions times four bytes: for 10 million 1,536-dimensional vectors that is about 61 GB before any graph **(derived arithmetic, from my vector-databases notes)**. HNSW trades recall for latency through `ef_search`, which can be turned live without a rebuild, while `m` and `ef_construction` are build-time commitments; int8 quantization then cuts memory about 4 times at the price of precision, which you repair by rescoring. A managed service removes index operations but turns a storage decision into a distributed-systems one, because every write must now land in two systems, and it moves your data outside your perimeter. I choose the operating model first, from my consistency and join requirements, and tune the index second, and I would settle it with recall and p99 measured on my own data at projected scale with real filters. The boundary of my claim is that I have run brute force only: I have not run HNSW, pgvector or Pinecone, and I have not measured recall of any approximate index, so those parts are learning targets.

How to talk about Ask AI here: its design document shows a Couchbase search index with a 1,536-dimension cosine vector field marked "optimized for recall" over 7,597 chunks **(design-doc snapshot)**. That is below my 10,000-chunk threshold, so brute force would have been defensible on scale alone; my reading, which the document does not state, is that the engine was chosen because the docs already live there and because it runs the vector and full-text search in one query.

**Follow-up they will ask:** How would you know your ANN index is silently losing recall?

**A:** I would sample about 1,000 real queries, compute the exact top K by brute force offline, store that as a fixture, and diff the index against it on a schedule, because approximate search fails silently with normal latency and a full result set. My in-memory retriever is exactly that baseline oracle, which is a useful side effect of having built it. Recall also falls as the corpus grows at a fixed `ef_search`, so a number measured on staging says little about production. The metric itself is small:

**Illustrative (not from the repo):**
```go
func recallAtK(approx, exact []string, k int) float64 {
	if k > len(exact) {
		k = len(exact)
	}
	if k == 0 {
		return 0
	}
	truth := make(map[string]bool, k)
	for _, id := range exact[:k] {
		truth[id] = true
	}
	hit := 0
	for i := 0; i < k && i < len(approx); i++ {
		if truth[approx[i]] {
			hit++
		}
	}
	return float64(hit) / float64(k)
}
```

How to talk about it: I say recall is under-measured because latency pages you and recall does not.

---

## Phase 5 — Retrieve

### 🟢 Beginner

**Q:** Why isn't plain vector search enough?

**A:** Vector search finds text with similar meaning, so it handles a paraphrase like "how do I make my database faster" very well. It is weak on exact strings such as an error code, a function name or a product SKU, because those have little learned meaning and get blurred into their neighbours. Keyword search, usually BM25, is the opposite: it matches the exact words and misses paraphrases. Hybrid search runs both and merges the results. In my own Agent Console I only built the vector half, and my notes list BM25 as the next build.

### 🟡 Intermediate

**Q:** What is reciprocal rank fusion, and how would you add hybrid search to your retriever?

**A:** Reciprocal rank fusion merges ranked lists by position instead of by score: each document gets the sum of 1 divided by (k plus its rank) across the lists, with k conventionally 60, which I would verify for my data. I use ranks because cosine similarity and BM25 scores are on different scales and cannot be added meaningfully. Because `Retriever` is an interface, I would add a `hybridRetriever` that composes a dense retriever and a sparse retriever and returns the fused top K. I wrote that in a scratch copy of the server, it compiled, and a small test passed showing that a chunk both lists agree on rises to the top; it is not committed to the repo.

**Illustrative (not from the repo):**
```go
const rrfK = 60

type hybridRetriever struct {
	dense, sparse Retriever
	fanout        int
}

func (h hybridRetriever) Retrieve(ctx context.Context, query string, k int) ([]Chunk, error) {
	byID := map[string]Chunk{}
	score := map[string]float64{}
	for _, src := range []Retriever{h.dense, h.sparse} {
		hits, err := src.Retrieve(ctx, query, h.fanout)
		if err != nil {
			return nil, err
		}
		for rank, c := range hits {
			byID[c.ID] = c
			score[c.ID] += 1.0 / float64(rrfK+rank+1)
		}
	}

	fused := make([]Chunk, 0, len(byID))
	for _, c := range byID {
		fused = append(fused, c)
	}
	sort.Slice(fused, func(i, j int) bool {
		a, b := fused[i], fused[j]
		if score[a.ID] != score[b.ID] {
			return score[a.ID] > score[b.ID]
		}
		return a.ID < b.ID
	})
	if k < len(fused) {
		fused = fused[:k]
	}
	return fused, nil
}
```

How to talk about it: I say it fails loudly if either retriever errors, which matches my rule that a retrieval failure must not quietly become a weaker answer. I also point at the stable tie-break, which my existing retriever has too:

**Source:** `AI/fe-hands-on/server/retriever.go:152-159`
```go
	// Sort by score desc, tie-broken by ID so results are stable across runs —
	// a nondeterministic retrieval order makes eval results impossible to diff.
	sort.SliceStable(ranked, func(i, j int) bool {
		if ranked[i].score != ranked[j].score {
			return ranked[i].score > ranked[j].score
		}
		return ranked[i].chunk.ID < ranked[j].chunk.ID
	})
```

### 🔴 Senior

**Q:** The right document is retrieved but ranked 14th and never reaches the prompt. What do you do?

**A:** I first confirm it is a ranking problem and not a recall problem by checking whether the right chunk is in the candidate pool at all, because a re-ranker can only reorder what the retriever returned. If it is in the pool, I retrieve wider, for example the top 20 to 100, and re-rank a short list down to K, using a cheap heuristic first and a cross-encoder only if measured quality justifies a model pass per candidate. Ask AI does its hybrid search in a single Couchbase query, falls back to pure vector search when hybrid returns nothing, applies a custom heuristic re-ranker that adds a length preference and content-type bonuses to the base score, and passes the top 5 to the model **(design-doc snapshot; I did not build or measure these parts)**. In my own rig the numbers say nothing about ranking quality: with 6 chunks and K=4, retrieval returned four of the six chunks for both the answerable and the unanswerable question **(run 2026-09)**, so no K sweep on that corpus is meaningful until I have a larger corpus and a golden retrieval set. I would also ablate every heuristic bonus against that golden set, because an unjustified bonus is just tunable noise.

**Follow-up they will ask:** Ask AI falls back silently when hybrid is empty. Isn't that the thing you criticise in your own prototype?

**A:** The two fallbacks are different in kind. Ask AI falls back to pure vector search, which is still grounded retrieval, and the design document says it logs which search type was used, so the degradation is visible. My prototype, when the vector query failed, fell back to a `LIKE '%query%'` search and reported a constant similarity of 1.0, which hides the failure behind a fake score. The principle I hold is that a fallback is acceptable if it stays grounded and is observable, and unacceptable if it pretends nothing happened.

**Source:** `RAG-app/server/couchbase.js:148-154`
```javascript
  } catch (error) {
    console.error('Error searching documents:', error);
    
    // Fallback to simple text search if vector search fails
    console.log('Falling back to text search...');
    return await fallbackTextSearch(query, limit);
  }
```

How to talk about it: I tell them I fixed this in the rewrite by making retrieval failure an error frame, which is the next phase.

---

## Phase 6 — Ground and generate

### 🟢 Beginner

**Q:** What does "grounding" mean, and how does the model know it is allowed to say "I don't know"?

**A:** Grounding means the answer must come from the passages I retrieved and not from the model's memory. The model only knows it may decline because I tell it so in the system prompt, in plain words. If I do not give that permission, the model tends to fill gaps with confident invention. In my build the prompt says to answer using only the context, to reply with a fixed sentence when the context does not contain the answer, and to cite sources by number.

### 🟡 Intermediate

**Q:** Show me how the prompt is assembled and how citations work.

**A:** `buildMessages` numbers each retrieved chunk as `[1]`, `[2]` and so on, together with its title and document ID, and injects that text into a server-owned system prompt, followed by the conversation. The prompt tells the model to cite by those numbers, and the same chunks go to the browser in a `sources` frame, so the UI can match a citation back to its evidence. The server rejects any client-supplied `system` message, because accepting one would let a web page overwrite the grounding rules. If there are no chunks, the code uses a separate, honest "no corpus configured" prompt instead of pretending to be grounded.

**Source:** `AI/fe-hands-on/server/stream.go:104-119`
```go
func buildMessages(chunks []Chunk, history []Message) []Message {
	var system string
	if len(chunks) == 0 {
		system = ungroundedSystemPrompt
	} else {
		var b strings.Builder
		for i, c := range chunks {
			// Numbered so the model can cite [1], [2] and the UI can match them
			// back to the sources frame.
			fmt.Fprintf(&b, "[%d] %s (%s)\n%s\n\n", i+1, c.Title, c.DocID, c.Text)
		}
		system = fmt.Sprintf(groundedSystemPrompt, strings.TrimSpace(b.String()))
	}

	return append([]Message{{Role: "system", Content: system}}, history...)
}
```

How to talk about it: I point at the `%s` template and say there are exactly two prompts and the server owns both. I also say that citations are requested by the prompt, and that I do not verify that a cited number actually exists.

**Q:** In what order do things happen on the wire, and why does the order matter?

**A:** The handler retrieves first, writes a `sources` frame before any token, then streams tokens, and ends with a `done` frame carrying usage. Sending sources first lets the UI show the evidence while the answer is still being written, and it also proves the citations are built from the same chunks that went into the prompt. If retrieval fails, the handler emits one `error` frame and returns without calling the model. A test asserts that the provider is never called in that case, because answering ungrounded without saying so is the dangerous path.

**Source:** `AI/fe-hands-on/server/stream.go:190-214`
```go
	// --- retrieve -----------------------------------------------------------
	var chunks []Chunk
	if s.retriever != nil {
		start := time.Now()

		var err error
		chunks, err = s.retriever.Retrieve(ctx, question, s.cfg.TopK)
		if err != nil {
			// Retrieval failure must not silently degrade into an ungrounded
			// answer — that is the confident-hallucination path. Fail loudly.
			log.Error("retrieval failed", "err", err)
			writeEvent(w, flusher, streamEvent{Type: "error", Value: "retrieval unavailable: " + err.Error()})
			return
		}

		log = log.With("retrieved", len(chunks), "retrieval_ms", time.Since(start).Milliseconds())

		sources := make([]Source, len(chunks))
		for i, c := range chunks {
			sources[i] = Source{ID: c.ID, DocID: c.DocID, Title: c.Title, Text: c.Text}
		}
		if err := writeEvent(w, flusher, streamEvent{Type: "sources", Sources: sources}); err != nil {
			return
		}
	}
```

**Source:** `AI/fe-hands-on/server/stream_test.go:139-157`
```go
func TestChatRetrievalFailureIsLoudNotSilentlyUngrounded(t *testing.T) {
	// The dangerous failure is answering ungrounded without saying so. If
	// retrieval breaks, the request must fail rather than quietly become a
	// parametric-memory answer.
	p := &stubProvider{tokens: []string{"should not run"}}
	r := &stubRetriever{err: errors.New("vector store down")}

	events := parseSSE(t, postChat(t, testServer(p, r), `{"messages":[{"role":"user","content":"hi"}]}`).Body.String())

	if len(events) != 1 || events[0].Type != "error" {
		t.Fatalf("events = %+v, want a single error frame", events)
	}
	if !strings.Contains(events[0].Value, "vector store down") {
		t.Errorf("error %q does not name the cause", events[0].Value)
	}
	if p.gotMsgs != nil {
		t.Error("provider was called despite retrieval failing — that is the silent-hallucination path")
	}
}
```

How to talk about it: the comment in the handler says retrieval failure must not silently degrade into an ungrounded answer, and the test name says the same thing; I use both to show the rule is enforced and not just stated.

### 🔴 Senior

**Q:** How do you handle refusal, citations and streaming, and what can still go wrong?

**A:** Refusal is a prompt contract, not a retrieval gate: for both my answerable and unanswerable questions retrieval returned four chunks, so the model declined because I permitted it to, not because retrieval found nothing. The measured effect is that the refusal used 9 completion tokens in both logged runs, against 162 tokens in one run and 128 in another for the answerable question, so I say "roughly 14 to 18 times fewer output tokens" and I do not quote a precise ratio **(run 2026-09, single samples, llama3.2:1b, CPU only)**. Streaming gives perceived speed but adds failure handling: if the client disconnects, the handler logs and stops without trying to write an error frame, and cancelling the request context aborts the upstream generation so I do not pay for tokens nobody reads. What can still go wrong is a list I can name: an empty retrieval result silently selects the ungrounded prompt, so if I add a similarity-score threshold I must change that branch; the retrieved text is placed in the system prompt without delimiting or sanitising, which is acceptable for first-party documentation and not for untrusted content such as customer tickets; and a model-written `[3]` is never checked against the sources list. The boundary is that I validated refusal on two golden cases with a 1B model, not on a broad adversarial set.

**Source:** `AI/fe-hands-on/server/stream.go:217-232`
```go
	emit := func(token string) error {
		return writeEvent(w, flusher, streamEvent{Type: "token", Value: token})
	}

	u, err := s.provider.Stream(ctx, buildMessages(chunks, req.Messages), emit)
	if err != nil {
		// A cancelled context means the client hung up; there is nobody left to
		// send an error frame to, so just record it.
		if r.Context().Err() != nil {
			log.Info("client disconnected", "err", err)
			return
		}
		log.Error("generation failed", "err", err)
		writeEvent(w, flusher, streamEvent{Type: "error", Value: err.Error()})
		return
	}
```

How to talk about it: I walk the disconnect branch, because it shows I thought about who is still listening.

**Follow-up they will ask:** How would you stop a fabricated citation or a prompt injection from retrieved content?

**A:** For citations I would parse the `[n]` markers from the finished answer, check that each n is within the number of sources, and emit a warning event or fail an eval when it is not. For injection I would wrap each chunk in clearly delimited, labelled blocks, tell the model that the contents are data and not instructions, and keep tools and secrets out of reach of that prompt, though I would measure with an injection test set instead of trusting the wrapping. Neither check is built in my repo today, and a delimiter is a mitigation, not a guarantee.

**Source:** `AI/fe-hands-on/server/stream.go:55-62`
```go
	for i, m := range r.Messages {
		switch m.Role {
		case "user", "assistant":
		default:
			// "system" is rejected on purpose: the server owns the system
			// prompt. Accepting one from the client is a prompt-injection hole.
			return fmt.Errorf("messages[%d].role must be \"user\" or \"assistant\", got %q", i, m.Role)
		}
```

How to talk about it: this is the client-side half of the story, where the server refuses a `system` role; the retrieved-content half is the gap I just described.

---

## Phase 7 — Cost, scale and swapping models without downtime

### 🟢 Beginner

**Q:** Where does the money go in a RAG system?

**A:** Almost all of it goes to the large language model that writes the answer, because you pay per token for both the prompt and the reply. Embedding is very cheap, so re-embedding the whole document set is a rounding error. There is also a fixed monthly cost for the database cluster that holds the vectors. In the Ask AI design document the model calls were about $0.0173 per request while the cluster was a fixed $208.80 per month **(design-doc snapshot, prices will have moved; verify in current docs)**.

### 🟡 Intermediate

**Q:** How do you swap the chat model, and how do you swap the embedding model, in your code?

**A:** The chat model is a config value behind the `provider` interface, so changing `OLLAMA_MODEL` and restarting is the whole change, and I verified a swap to `qwen2.5:1.5b` with no code change **(run 2026-09)**. The embedding model is different because it is stateful: `EMBED_MODEL` must match the model that indexed the corpus, and my retriever holds the embedder together with the chunks, so a freshly built retriever carries its own query embedder and the pair always moves as one unit. My server does not do a live swap today; it re-embeds at boot, so a swap means a restart. The Illustrative snippet below shows how I would promote a new, fully built index in one atomic step.

**Source:** `AI/fe-hands-on/server/config.go:14-25`
```go
type Config struct {
	Addr           string
	AllowedOrigins []string // CORS allowlist; "*" only if explicitly configured
	Provider       string   // "ollama" | "fake"
	OllamaURL      string
	ChatModel      string
	EmbedModel     string
	CorpusDir      string        // empty disables retrieval
	TopK           int           // chunks handed to the model
	RequestTimeout time.Duration // upper bound on one generation
	ShutdownGrace  time.Duration
}
```

**Source:** `AI/fe-hands-on/server/retriever.go:93-96`
```go
type memoryRetriever struct {
	embedder Embedder
	chunks   []Chunk // each carries its own normalized vector
}
```

**Illustrative (not from the repo):**
```go
type swappableRetriever struct {
	live atomic.Pointer[memoryRetriever]
}

func (s *swappableRetriever) Retrieve(ctx context.Context, query string, k int) ([]Chunk, error) {
	return s.live.Load().Retrieve(ctx, query, k)
}

func (s *swappableRetriever) Promote(next *memoryRetriever) {
	s.live.Store(next)
}
```

How to talk about it: I say the snippet compiled and passed a small test in a scratch copy, that the index and its query embedder flip together, and that in production I would add a validation step on a golden set before calling `Promote`.

### 🔴 Senior

**Q:** How do you swap an embedding model with zero downtime, and how do you reason about cost and scale?

**A:** A new embedding model means a new vector space, so I never update in place: I build a second, versioned index beside the live one, backfill it, shadow-read live queries against it without serving them, compare quality offline, flip behind a flag, and keep the old index warm for rollback. The cost is not the embedding calls, since a full re-embed in the design document was about $0.12 per pass **(design-doc snapshot)**, so the real constraints are validation and rollback. For the chat model the swap is easier, and my server already supports a rolling restart because it stops accepting connections on SIGTERM and gives in-flight streams a grace period to finish. On cost, I derive from the document's own per-call figures about $0.01732 per request and a crossover near 12,000 requests per month, below which the fixed cluster dominates and above which token spend does **(derived; verify current prices)**. The rephrasing call is about a third of that model spend **(derived)**, and the document's printed rephrasing figure of $589.25 per million requests looks like a typo for $5,892.50 by its own arithmetic, which I would confirm with the source spreadsheet. The boundary is that I have never run two instances behind a load balancer, my index is not persisted, and extrapolating my 535 ms boot embed to a large corpus is not something I claim.

**Source:** `AI/fe-hands-on/server/main.go:72-90`
```go
	// Graceful shutdown: stop accepting new connections, then give in-flight
	// streams a chance to finish rather than cutting answers off mid-sentence.
	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)

		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig

		log.Info("shutdown signal received", "grace", cfg.ShutdownGrace.String())

		ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownGrace)
		defer cancel()

		if err := httpServer.Shutdown(ctx); err != nil {
			log.Error("graceful shutdown failed", "err", err)
		}
	}()
```

How to talk about it: the shutdown goroutine is what makes a rolling restart safe for streaming responses, and I say it is a necessary condition for zero downtime, not the whole story.

**Follow-up they will ask:** How would you cut the cost of this system by half?

**A:** In order of leverage I would add a semantic cache for repeated questions, which the design document lists as a future improvement, then shrink the rephrasing call by using a smaller model and fewer history turns than the current five, then tighten K and the prompt, and only then look at the generation model. Each change goes through the golden set first, so quality is measured, not assumed. The design document also describes per-tenant limits on calls per minute, requests per day and tokens per month, with free and paid tiers differing **(design-doc snapshot)**; my own server has no authentication or rate limiting, and its README says so.

---

## Code reference index

| path:lines | what it shows |
|---|---|
| `AI/fe-hands-on/server/main.go:3-13` | Architecture comment: request flow and the three seams (provider, Retriever, SSE contract) |
| `AI/fe-hands-on/server/stream.go:81-95` | groundedSystemPrompt: the permitted-refusal line, citation rule, context slot |
| `AI/fe-hands-on/server/corpus.go:34-62` | LoadCorpus: recursive .md walk, wrapped errors, relative DocID |
| `AI/fe-hands-on/server/corpus_test.go:121-142` | Test: only Markdown read, subdirs recursed, DocIDs never absolute |
| `AI/fe-hands-on/server/main.go:130-140` | Missing/empty corpus is survived loudly (warn: answers ungrounded) |
| `AI/fe-hands-on/server/corpus.go:101-115` | headingText and its documented fenced-code limitation |
| `AI/fe-hands-on/server/corpus.go:120-143` | splitLong: paragraph accumulation against the 900-character soft budget |
| `AI/fe-hands-on/server/retriever.go:105-111` | Heading prepended to chunk text before embedding |
| `AI/fe-hands-on/server/retriever.go:118-124` | Vectors normalized once at index time |
| `AI/fe-hands-on/server/retriever.go:190-203` | dot: cosine for unit vectors; mismatched lengths score 0 |
| `RAG-app/server/couchbase.js:92-94` | Prototype embeds the whole document, no chunking |
| `AI/fe-hands-on/server/retriever.go:13-19` | Retriever interface: the store swap seam |
| `AI/fe-hands-on/server/retriever.go:142-150` | Brute-force scoring loop over every chunk |
| `RAG-app/server/couchbase.js:127-133` | Prototype SQL++ VECTOR_DISTANCE query (engine does the scoring) |
| `RAG-app/server/couchbase.js:57-66` | Prototype index check: only warns if no vector index found |
| `AI/fe-hands-on/server/retriever.go:152-159` | Stable sort, ties broken by chunk ID |
| `RAG-app/server/couchbase.js:148-154` | Prototype silently falls back to text search on any vector error |
| `AI/fe-hands-on/server/stream.go:104-119` | buildMessages: numbered sources, server-owned system prompt, ungrounded fallback |
| `AI/fe-hands-on/server/stream.go:190-214` | Retrieve stage: loud failure, sources frame before any token |
| `AI/fe-hands-on/server/stream_test.go:139-157` | Test: retrieval failure is an error frame and the provider is never called |
| `AI/fe-hands-on/server/stream.go:217-232` | Generate stage and client-disconnect branch |
| `AI/fe-hands-on/server/stream.go:55-62` | Validation rejects client-supplied system messages |
| `AI/fe-hands-on/server/config.go:14-25` | Config: EmbedModel, TopK, CorpusDir and friends |
| `AI/fe-hands-on/server/retriever.go:93-96` | memoryRetriever holds the embedder together with its chunks |
| `AI/fe-hands-on/server/main.go:72-90` | Graceful shutdown that lets in-flight streams finish |
| `AI/docs/Ask AI design document.md:553-596` | Hybrid search with re-ranking, fallback, K=5 (section 4.4.5) [P] |
| `AI/docs/Ask AI design document.md:627-655` | Weekly embedding pipeline, 5-6 h to ~20 min with 10 goroutines (section 4.4.7) [P] |
| `AI/docs/Ask AI design document.md:657-669` | Context-aware rephrasing with a lightweight LLM (section 4.4.8) [P] |
| `AI/docs/Ask AI design document.md:736-776` | Model and embedding cost tables, 2,667 docs to 7,597 chunks (section 6.1) [P] |
| `AI/docs/Ask AI design document.md:914-938` | Total monthly cost, $208.80 cluster (section 6.3) [P] |
| `AI/docs/notes/03-grounded-rag-agent-console.md:81-96` | Measured run: 6 chunks in 535 ms, token counts, refusal path |
| `AI/docs/notes/ai-lifecycle-business-cases.md:372-442` | Cost curve derivation and the 2026-09-07 measured serving run |
| `AI/fe-hands-on/README.md:89-111` | Why brute force, grounding result, failure modes, known limits |
| `AI/interviews/vector-databases/answers.md:239-248` | A18: pgvector vs Pinecone vs Couchbase operating models |
| `AI/interviews/vector-databases/answers.md:686-691` | AB1: building a recall baseline from sampled queries |

## Self-check

1. **What are the two paths in a RAG system and what is the one place they must agree?** The write path (ingest, chunk, embed) and the read path (embed query, retrieve, generate) must use the same embedding model.
2. **Why is brute force the right index in my build?** Under roughly 10,000 chunks it is exact, has no tuning knob, and my scratch benchmark put it near 14 ms at 10,000 vectors.
3. **Why does my handler emit `sources` before the first token and an `error` frame on retrieval failure?** The reader sees evidence while the answer streams, and a silent fallback to an ungrounded answer is the worst failure.
4. **What do I need before I can claim hybrid search or a re-ranker helps?** A golden retrieval set with recall@K measured before and after, which I have not built yet.
5. **What does an embedding model change force?** A full re-embed into a new versioned index, a shadow-read comparison, a flip together with the query embedder, and a warm rollback, because old and new vectors are not comparable.

## What not to claim

- Do not say I designed or built Ask AI; I am a contributor, and hybrid search, the heuristic re-ranker, K=5 and the weekly job are described in a design document written by others. Be ready to state exactly which parts I touched, which these documents do not record.
- Do not say my build has hybrid search, BM25, RRF or re-ranking; they exist only as an Illustrative scratch snippet.
- Do not claim experience with HNSW tuning, pgvector or Pinecone, or any measured recall of an approximate index; those are forward-looking learning targets.
- Do not quote the benchmark numbers (14 ms, 165 ms) as real-world: they are random 768-dimensional vectors on one machine with a full sort.
- Do not generalise the refusal result: one 1B model, a 6-chunk corpus, two golden cases, and single-sample token counts that varied between runs (162 vs 128).
- Do not quote Ask AI costs or OpenAI prices as current; they are a March 2025 snapshot, and the $5,892.50 correction is my derivation.
- Do not claim zero-downtime swaps, persistence, authentication or rate limiting in my server; the README lists them as known limits.
- Do not claim retrieval is evaluated: the current golden cases supply fixed context, so they test generation and not retrieval.
- Do not state external facts (pgvector 0.8.0 iterative scans, Couchbase 8.0 index types, RRF k=60 as a default, current model names) without saying "verify in current docs".
- Do not quote any code from the couchbase-cloud monorepo.
