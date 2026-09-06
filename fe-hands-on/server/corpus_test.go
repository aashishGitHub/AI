package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestChunkMarkdownSplitsOnHeadings(t *testing.T) {
	doc := `# Primary indexes

Use CREATE PRIMARY INDEX.

# Secondary indexes

Use CREATE INDEX.`

	chunks := chunkMarkdown("indexes.md", doc)

	if len(chunks) != 2 {
		t.Fatalf("got %d chunks, want 2 (one per heading): %+v", len(chunks), chunks)
	}
	if chunks[0].Title != "Primary indexes" || chunks[1].Title != "Secondary indexes" {
		t.Errorf("titles = %q, %q", chunks[0].Title, chunks[1].Title)
	}
	if !strings.Contains(chunks[0].Text, "CREATE PRIMARY INDEX") {
		t.Errorf("chunk 0 lost its body: %q", chunks[0].Text)
	}
	// Citation needs a stable, unique id per chunk.
	if chunks[0].ID == chunks[1].ID {
		t.Errorf("chunk ids collide: %q", chunks[0].ID)
	}
	for _, c := range chunks {
		if c.DocID != "indexes.md" {
			t.Errorf("docID = %q, want indexes.md", c.DocID)
		}
	}
}

func TestChunkMarkdownKeepsPreambleBeforeFirstHeading(t *testing.T) {
	chunks := chunkMarkdown("doc.md", "Intro text with no heading.\n\n# Later\n\nBody.")

	if len(chunks) != 2 {
		t.Fatalf("got %d chunks, want 2; preamble must not be dropped", len(chunks))
	}
	if !strings.Contains(chunks[0].Text, "Intro text") {
		t.Errorf("preamble lost: %q", chunks[0].Text)
	}
}

func TestChunkMarkdownSplitsOverlongSectionsOnParagraphs(t *testing.T) {
	// Each paragraph is individually identifiable by a unique start and end
	// marker, so a chunk holding one without the other proves a mid-paragraph
	// cut. A fixture repeating a single word cannot detect that.
	paras := []string{
		"ALPHA-START " + strings.Repeat("a ", 200) + "ALPHA-END",
		"BETA-START " + strings.Repeat("b ", 200) + "BETA-END",
		"GAMMA-START " + strings.Repeat("c ", 200) + "GAMMA-END",
	}
	chunks := chunkMarkdown("big.md", "# Big\n\n"+strings.Join(paras, "\n\n"))

	if len(chunks) < 2 {
		t.Fatalf("got %d chunks, want the section split (target %d chars)", len(chunks), chunkTarget)
	}

	for _, name := range []string{"ALPHA", "BETA", "GAMMA"} {
		for i, c := range chunks {
			hasStart := strings.Contains(c.Text, name+"-START")
			hasEnd := strings.Contains(c.Text, name+"-END")
			if hasStart != hasEnd {
				t.Errorf("chunk %d split paragraph %s mid-way (start=%v end=%v)", i, name, hasStart, hasEnd)
			}
		}
	}

	// And nothing may be silently dropped on the way through.
	all := strings.Join(func() []string {
		out := make([]string, len(chunks))
		for i, c := range chunks {
			out[i] = c.Text
		}
		return out
	}(), "\n")
	for _, name := range []string{"ALPHA", "BETA", "GAMMA"} {
		if !strings.Contains(all, name+"-END") {
			t.Errorf("paragraph %s was dropped entirely", name)
		}
	}
}

func TestChunkMarkdownIgnoresEmptyDocuments(t *testing.T) {
	if got := chunkMarkdown("empty.md", "\n\n   \n"); len(got) != 0 {
		t.Errorf("got %d chunks from a blank document, want 0", len(got))
	}
}

func TestHeadingText(t *testing.T) {
	tests := []struct {
		line     string
		want     string
		isHeader bool
	}{
		{"# Title", "Title", true},
		{"### Deep", "Deep", true},
		{"  ## Indented", "Indented", true},
		{"Not a heading", "", false},
		{"#", "", false},     // bare hash is not a heading
		{"#    ", "", false}, // nor is one with only spaces
	}

	for _, tc := range tests {
		got, ok := headingText(tc.line)
		if ok != tc.isHeader || got != tc.want {
			t.Errorf("headingText(%q) = (%q, %v), want (%q, %v)", tc.line, got, ok, tc.want, tc.isHeader)
		}
	}
}

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

func TestLoadCorpusMissingDirIsAnError(t *testing.T) {
	if _, err := LoadCorpus(filepath.Join(t.TempDir(), "nope")); err == nil {
		t.Fatal("LoadCorpus error = nil for a missing directory")
	}
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

func TestConfigValidate(t *testing.T) {
	valid := Config{Provider: "ollama", OllamaURL: "http://x", TopK: 4, AllowedOrigins: []string{"http://localhost:3000"}}

	tests := []struct {
		name    string
		mutate  func(*Config)
		wantErr bool
	}{
		{"valid", func(*Config) {}, false},
		{"fake provider needs no url", func(c *Config) { c.Provider, c.OllamaURL = "fake", "" }, false},
		{"unknown provider", func(c *Config) { c.Provider = "openai" }, true},
		{"topK below one", func(c *Config) { c.TopK = 0 }, true},
		{"ollama without url", func(c *Config) { c.OllamaURL = "" }, true},
		{"blank origin", func(c *Config) { c.AllowedOrigins = []string{"http://a", " "} }, true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			c := valid
			c.AllowedOrigins = append([]string(nil), valid.AllowedOrigins...)
			tc.mutate(&c)

			if err := c.Validate(); (err != nil) != tc.wantErr {
				t.Errorf("Validate() error = %v, wantErr %v", err, tc.wantErr)
			}
		})
	}
}

func TestLoadConfigRejectsUnparseableValues(t *testing.T) {
	t.Setenv("TOP_K", "not-a-number")
	if _, err := LoadConfig(); err == nil {
		t.Fatal("LoadConfig error = nil; a bad TOP_K must stop startup, not surface per request")
	}
}

func TestLoadConfigDefaults(t *testing.T) {
	for _, k := range []string{"ADDR", "PROVIDER", "TOP_K", "REQUEST_TIMEOUT", "CORPUS_DIR", "ALLOWED_ORIGINS"} {
		t.Setenv(k, "")
	}

	c, err := LoadConfig()
	if err != nil {
		t.Fatalf("LoadConfig: %v", err)
	}
	if c.Addr != ":8080" || c.Provider != "ollama" || c.TopK != 4 {
		t.Errorf("defaults = %+v", c)
	}
	if c.RequestTimeout != 120*time.Second {
		t.Errorf("RequestTimeout = %v, want 2m", c.RequestTimeout)
	}
	if !c.RetrievalEnabled() {
		t.Error("retrieval should be enabled by default")
	}
}

func TestRetrievalDisabledWhenCorpusDirEmpty(t *testing.T) {
	if (Config{CorpusDir: ""}).RetrievalEnabled() {
		t.Error("RetrievalEnabled() = true with no corpus dir")
	}
}
