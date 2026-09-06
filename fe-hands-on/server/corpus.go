package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Chunk is one retrievable unit: the granularity at which the corpus is
// embedded, searched, and cited.
//
// Chunking sets the ceiling on retrieval quality before any index parameter is
// touched — a perfect index over bad chunks retrieves exactly the wrong thing,
// reliably. Too small and each chunk is precise but context-free; too large and
// the embedding averages several topics into a blurred centroid matching
// nothing sharply. See interviews/vector-databases/answers.md A37.
type Chunk struct {
	ID     string    `json:"id"`
	DocID  string    `json:"docId"` // source file, for citation
	Title  string    `json:"title"` // nearest preceding heading
	Text   string    `json:"text"`
	Vector []float32 `json:"-"` // never serialized to the client
}

// chunkTarget is a soft character budget per chunk. Sections under this stay
// whole so a short document is never split mid-thought.
const chunkTarget = 900

// LoadCorpus reads every .md file under dir and splits it into chunks along
// Markdown headings, which is the cheapest structure-aware boundary available:
// a heading is an author-declared topic break, so it is a far better split point
// than a fixed character count.
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

// chunkMarkdown splits one document into heading-delimited sections, then
// further splits any section that overruns chunkTarget on paragraph boundaries.
func chunkMarkdown(docID, content string) []Chunk {
	var (
		chunks  []Chunk
		title   = docID
		section []string
	)

	flush := func() {
		text := strings.TrimSpace(strings.Join(section, "\n"))
		section = section[:0]
		if text == "" {
			return
		}
		for _, part := range splitLong(text) {
			chunks = append(chunks, Chunk{
				ID:    fmt.Sprintf("%s#%d", docID, len(chunks)),
				DocID: docID,
				Title: title,
				Text:  part,
			})
		}
	}

	for _, line := range strings.Split(content, "\n") {
		if heading, ok := headingText(line); ok {
			flush() // the previous section ends where the next heading begins
			title = heading
		}
		section = append(section, line)
	}
	flush()

	return chunks
}

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

// splitLong breaks an over-long section on blank lines, accumulating paragraphs
// until the budget is reached. Splitting between paragraphs rather than at a
// character offset avoids cutting a sentence — or a code fence — in half.
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
