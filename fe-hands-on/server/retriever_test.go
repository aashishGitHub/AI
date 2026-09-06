package main

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// stubEmbedder maps text to a fixed vector, so retrieval ranking is exact and
// testable without a model server.
type stubEmbedder struct {
	vectors map[string][]float32
	err     error
	calls   int
}

func (s *stubEmbedder) Embed(_ context.Context, texts []string) ([][]float32, error) {
	s.calls++
	if s.err != nil {
		return nil, s.err
	}

	out := make([][]float32, len(texts))
	for i, t := range texts {
		for key, vec := range s.vectors {
			if strings.Contains(t, key) {
				out[i] = vec
				break
			}
		}
		if out[i] == nil {
			out[i] = []float32{0, 0, 1} // orthogonal to the fixtures below
		}
	}
	return out, nil
}

func TestNormalizeProducesUnitVector(t *testing.T) {
	got := normalize([]float32{3, 4}) // 3-4-5 triangle

	var sum float64
	for _, v := range got {
		sum += float64(v) * float64(v)
	}
	if math.Abs(math.Sqrt(sum)-1) > 1e-6 {
		t.Errorf("magnitude = %v, want 1", math.Sqrt(sum))
	}
	if math.Abs(float64(got[0])-0.6) > 1e-6 || math.Abs(float64(got[1])-0.8) > 1e-6 {
		t.Errorf("normalize([3 4]) = %v, want [0.6 0.8]", got)
	}
}

func TestNormalizeZeroVectorDoesNotDivideByZero(t *testing.T) {
	got := normalize([]float32{0, 0, 0})
	for _, v := range got {
		if math.IsNaN(float64(v)) {
			t.Fatalf("normalize produced NaN: %v", got)
		}
	}
}

func TestDotMismatchedLengthsScoresZero(t *testing.T) {
	// Only happens when two different embedding models were used. Scoring 0
	// keeps the chunk out of results instead of taking the server down.
	if got := dot([]float32{1, 0}, []float32{1, 0, 0}); got != 0 {
		t.Errorf("dot with mismatched dims = %v, want 0", got)
	}
}

func TestRetrieveRanksBySimilarityAndRespectsK(t *testing.T) {
	embedder := &stubEmbedder{vectors: map[string][]float32{
		"indexes": {1, 0, 0},
		"buckets": {0, 1, 0},
		"query":   {1, 0, 0}, // identical to "indexes"
	}}

	chunks := []Chunk{
		{ID: "a", Title: "indexes", Text: "indexes"},
		{ID: "b", Title: "buckets", Text: "buckets"},
	}

	r, err := NewMemoryRetriever(context.Background(), embedder, chunks)
	if err != nil {
		t.Fatalf("NewMemoryRetriever: %v", err)
	}
	if r.Len() != 2 {
		t.Fatalf("indexed %d chunks, want 2", r.Len())
	}

	got, err := r.Retrieve(context.Background(), "query", 1)
	if err != nil {
		t.Fatalf("Retrieve: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("got %d chunks, want 1 (k must be respected)", len(got))
	}
	if got[0].ID != "a" {
		t.Errorf("top chunk = %q, want %q (nearest vector)", got[0].ID, "a")
	}
}

func TestRetrieveClampsKToCorpusSize(t *testing.T) {
	embedder := &stubEmbedder{vectors: map[string][]float32{"only": {1, 0, 0}}}
	r, _ := NewMemoryRetriever(context.Background(), embedder, []Chunk{{ID: "a", Text: "only"}})

	got, err := r.Retrieve(context.Background(), "only", 10) // ask for more than exist
	if err != nil {
		t.Fatalf("Retrieve: %v", err)
	}
	if len(got) != 1 {
		t.Errorf("got %d chunks, want 1", len(got))
	}
}

func TestRetrieveIsDeterministicOnTiedScores(t *testing.T) {
	// Identical vectors must break ties by ID, otherwise eval results are not
	// diffable between runs.
	embedder := &stubEmbedder{vectors: map[string][]float32{"same": {1, 0, 0}}}
	chunks := []Chunk{{ID: "z", Text: "same"}, {ID: "a", Text: "same"}, {ID: "m", Text: "same"}}
	r, _ := NewMemoryRetriever(context.Background(), embedder, chunks)

	for i := 0; i < 5; i++ {
		got, _ := r.Retrieve(context.Background(), "same", 3)
		if got[0].ID != "a" || got[1].ID != "m" || got[2].ID != "z" {
			t.Fatalf("run %d order = %s,%s,%s; want a,m,z", i, got[0].ID, got[1].ID, got[2].ID)
		}
	}
}

func TestRetrieveSurfacesEmbedderFailure(t *testing.T) {
	embedder := &stubEmbedder{vectors: map[string][]float32{"x": {1, 0, 0}}}
	r, _ := NewMemoryRetriever(context.Background(), embedder, []Chunk{{ID: "a", Text: "x"}})

	embedder.err = errors.New("model unreachable")
	if _, err := r.Retrieve(context.Background(), "x", 1); err == nil {
		t.Fatal("Retrieve error = nil; a failed query embedding must not look like 'no results'")
	}
}

func TestEmptyCorpusRetrievesNothingWithoutCallingTheModel(t *testing.T) {
	embedder := &stubEmbedder{}
	r, err := NewMemoryRetriever(context.Background(), embedder, nil)
	if err != nil {
		t.Fatalf("NewMemoryRetriever: %v", err)
	}

	got, err := r.Retrieve(context.Background(), "anything", 5)
	if err != nil || got != nil {
		t.Errorf("got (%v, %v), want (nil, nil)", got, err)
	}
	if embedder.calls != 0 {
		t.Errorf("embedder called %d times on an empty corpus, want 0", embedder.calls)
	}
}

func TestOllamaEmbedderParsesResponse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/embed" {
			t.Errorf("path = %q, want /api/embed", r.URL.Path)
		}

		var body struct {
			Model string   `json:"model"`
			Input []string `json:"input"`
		}
		json.NewDecoder(r.Body).Decode(&body)
		if len(body.Input) != 2 {
			t.Errorf("input length = %d, want 2 (must batch)", len(body.Input))
		}

		json.NewEncoder(w).Encode(map[string]any{
			"embeddings": [][]float32{{1, 2, 3}, {4, 5, 6}},
		})
	}))
	defer srv.Close()

	e := ollamaEmbedder{baseURL: srv.URL, model: "test", client: srv.Client()}
	got, err := e.Embed(context.Background(), []string{"a", "b"})
	if err != nil {
		t.Fatalf("Embed: %v", err)
	}
	if len(got) != 2 || got[1][2] != 6 {
		t.Errorf("embeddings = %v, want [[1 2 3] [4 5 6]]", got)
	}
}

func TestOllamaEmbedderRejectsCountMismatch(t *testing.T) {
	// A silent count mismatch would misalign vectors with chunks — every
	// citation would point at the wrong document.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"embeddings": [][]float32{{1, 2, 3}}})
	}))
	defer srv.Close()

	e := ollamaEmbedder{baseURL: srv.URL, model: "test", client: srv.Client()}
	if _, err := e.Embed(context.Background(), []string{"a", "b"}); err == nil {
		t.Fatal("Embed error = nil, want a mismatch error for 1 vector / 2 inputs")
	}
}

func TestOllamaEmbedderReportsHTTPFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "model not found", http.StatusNotFound)
	}))
	defer srv.Close()

	e := ollamaEmbedder{baseURL: srv.URL, model: "missing", client: srv.Client()}
	_, err := e.Embed(context.Background(), []string{"a"})
	if err == nil || !strings.Contains(err.Error(), "404") {
		t.Errorf("err = %v, want one mentioning 404", err)
	}
}
