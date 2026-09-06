package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"sort"
)

// Retriever finds the chunks most relevant to a query. It is an interface for
// the same reason `provider` is: the store is a swap seam. An in-memory brute
// force store today, Couchbase or pgvector later, with nothing above this line
// needing to change.
type Retriever interface {
	Retrieve(ctx context.Context, query string, k int) ([]Chunk, error)
}

// Embedder turns text into vectors. Separated from Retriever because the same
// embedder must serve BOTH the write path (indexing the corpus) and the read
// path (embedding the query) — using different models on those two paths
// produces vectors from different spaces, which no system will warn you about.
type Embedder interface {
	Embed(ctx context.Context, texts []string) ([][]float32, error)
}

// ---------------------------------------------------------------------------
// Ollama embeddings
// ---------------------------------------------------------------------------

type ollamaEmbedder struct {
	baseURL string
	model   string
	client  *http.Client
}

func (e ollamaEmbedder) Embed(ctx context.Context, texts []string) ([][]float32, error) {
	if len(texts) == 0 {
		return nil, nil
	}

	body, err := json.Marshal(map[string]any{"model": e.model, "input": texts})
	if err != nil {
		return nil, fmt.Errorf("encode embed request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, e.baseURL+"/api/embed", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("build embed request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := e.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("call embed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("embed returned %s", resp.Status)
	}

	var decoded struct {
		Embeddings [][]float32 `json:"embeddings"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		return nil, fmt.Errorf("decode embed response: %w", err)
	}
	if len(decoded.Embeddings) != len(texts) {
		return nil, fmt.Errorf("embed returned %d vectors for %d inputs", len(decoded.Embeddings), len(texts))
	}
	return decoded.Embeddings, nil
}

// ---------------------------------------------------------------------------
// In-memory brute-force store
// ---------------------------------------------------------------------------

// memoryRetriever scores the query against every chunk — exact search, no ANN
// index at all.
//
// This is a deliberate choice, not a shortcut. Below roughly 10K chunks an ANN
// index buys nothing: brute force is exact (100% recall by construction),
// has no build step, no tuning knob, and no recall to silently lose. Reaching
// for HNSW at this size is the mistake, not the sophistication. See
// interviews/vector-databases/answers.md A44.
//
// When the corpus outgrows that, the Retriever interface is where a real vector
// store slots in — and the operating-model question (where vectors live
// relative to the rest of the data) gets decided then, on its merits.
type memoryRetriever struct {
	embedder Embedder
	chunks   []Chunk // each carries its own normalized vector
}

// NewMemoryRetriever embeds the corpus once, up front. Embedding is the slow
// part of indexing, so it happens at startup rather than per request.
func NewMemoryRetriever(ctx context.Context, embedder Embedder, chunks []Chunk) (*memoryRetriever, error) {
	if len(chunks) == 0 {
		return &memoryRetriever{embedder: embedder}, nil
	}

	texts := make([]string, len(chunks))
	for i, c := range chunks {
		// Prepending the heading gives the embedding topical context the chunk
		// body may not restate — a section that says "run this command" is
		// meaningless without the heading it sits under.
		texts[i] = c.Title + "\n\n" + c.Text
	}

	vectors, err := embedder.Embed(ctx, texts)
	if err != nil {
		return nil, fmt.Errorf("embed corpus: %w", err)
	}

	indexed := make([]Chunk, len(chunks))
	for i := range chunks {
		indexed[i] = chunks[i]
		// Normalize once at index time so query-time scoring is a plain dot
		// product: cosine similarity without repeating the division per query.
		indexed[i].Vector = normalize(vectors[i])
	}

	return &memoryRetriever{embedder: embedder, chunks: indexed}, nil
}

func (r *memoryRetriever) Len() int { return len(r.chunks) }

func (r *memoryRetriever) Retrieve(ctx context.Context, query string, k int) ([]Chunk, error) {
	if len(r.chunks) == 0 {
		return nil, nil
	}

	vectors, err := r.embedder.Embed(ctx, []string{query})
	if err != nil {
		return nil, fmt.Errorf("embed query: %w", err)
	}
	q := normalize(vectors[0])

	type scored struct {
		chunk Chunk
		score float64
	}

	ranked := make([]scored, 0, len(r.chunks))
	for _, c := range r.chunks {
		ranked = append(ranked, scored{chunk: c, score: dot(q, c.Vector)})
	}

	// Sort by score desc, tie-broken by ID so results are stable across runs —
	// a nondeterministic retrieval order makes eval results impossible to diff.
	sort.SliceStable(ranked, func(i, j int) bool {
		if ranked[i].score != ranked[j].score {
			return ranked[i].score > ranked[j].score
		}
		return ranked[i].chunk.ID < ranked[j].chunk.ID
	})

	if k > len(ranked) {
		k = len(ranked)
	}
	out := make([]Chunk, k)
	for i := range out {
		out[i] = ranked[i].chunk
	}
	return out, nil
}

// normalize returns a unit-length copy, so cosine similarity reduces to a dot
// product. Returns the input unchanged if it has no magnitude.
func normalize(v []float32) []float32 {
	var sum float64
	for _, x := range v {
		sum += float64(x) * float64(x)
	}
	if sum == 0 {
		return v
	}
	norm := math.Sqrt(sum)

	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = float32(float64(x) / norm)
	}
	return out
}

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
