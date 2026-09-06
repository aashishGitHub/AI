package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// Message is one turn of a conversation. Carrying a slice of these rather than
// a single prompt string is what makes multi-turn possible; the provider stays
// stateless and the caller owns the history.
type Message struct {
	Role    string `json:"role"` // "system" | "user" | "assistant"
	Content string `json:"content"`
}

// usage rides on the terminating done frame so the console can show real cost
// and latency per turn. You cannot tune what you do not measure.
type usage struct {
	PromptTokens     int   `json:"promptTokens"`
	CompletionTokens int   `json:"completionTokens"`
	LatencyMs        int64 `json:"latencyMs"`
}

// provider turns a conversation into a stream of tokens. Implementations push
// each token through emit as it arrives and must not buffer the whole response,
// because time-to-first-token is the entire point of streaming.
//
// ctx carries client disconnection; honouring it stops the upstream generation
// instead of paying for tokens nobody will read.
type provider interface {
	Stream(ctx context.Context, messages []Message, emit func(token string) error) (usage, error)
}

// ---------------------------------------------------------------------------
// fakeProvider — deterministic, no model server
// ---------------------------------------------------------------------------

// fakeProvider replays a canned sentence word by word. It keeps the frontend
// and the SSE plumbing developable with no model running, and makes transport
// tests deterministic — the same reason an eval suite runs its cheap
// deterministic assertion before its model-graded one.
type fakeProvider struct{}

const fakeResponse = "Server-sent events let the server push tokens to the browser over a single long-lived HTTP connection."

func (fakeProvider) Stream(ctx context.Context, _ []Message, emit func(string) error) (usage, error) {
	start := time.Now()
	words := strings.Fields(fakeResponse)

	for _, word := range words {
		select {
		case <-ctx.Done():
			return usage{}, ctx.Err()
		case <-time.After(120 * time.Millisecond): // simulate generation pace
		}
		if err := emit(word + " "); err != nil {
			return usage{}, err
		}
	}

	return usage{CompletionTokens: len(words), LatencyMs: time.Since(start).Milliseconds()}, nil
}

// ---------------------------------------------------------------------------
// ollamaProvider — NDJSON → token adapter
// ---------------------------------------------------------------------------

// ollamaProvider streams from Ollama's /api/chat, which returns NDJSON — one
// JSON object per line — rather than SSE. Translating that into our own event
// contract is exactly the work a provider exists to encapsulate: every vendor
// has a different streaming dialect and none of it should reach the frontend.
type ollamaProvider struct {
	baseURL string
	model   string
	client  *http.Client
}

// ollamaFrame is one NDJSON line. The final frame carries done:true plus the
// token counts for the whole request.
type ollamaFrame struct {
	Message struct {
		Content string `json:"content"`
	} `json:"message"`
	Done            bool `json:"done"`
	PromptEvalCount int  `json:"prompt_eval_count"` // prompt tokens
	EvalCount       int  `json:"eval_count"`        // completion tokens
}

func (o ollamaProvider) Stream(ctx context.Context, messages []Message, emit func(string) error) (usage, error) {
	start := time.Now()

	body, err := json.Marshal(map[string]any{
		"model":    o.model,
		"messages": messages,
		"stream":   true,
		// Temperature 0 keeps answers reproducible, which is what makes an eval
		// suite able to tell a real regression from ordinary sampling noise.
		"options": map[string]any{"temperature": 0},
	})
	if err != nil {
		return usage{}, fmt.Errorf("encode request: %w", err)
	}

	// NewRequestWithContext is the line that propagates client disconnection
	// upstream: cancelling ctx aborts the in-flight generation.
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, o.baseURL+"/api/chat", bytes.NewReader(body))
	if err != nil {
		return usage{}, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := o.client.Do(req)
	if err != nil {
		return usage{}, fmt.Errorf("call ollama: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return usage{}, fmt.Errorf("ollama returned %s", resp.Status)
	}

	var u usage
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024) // headroom for a long token

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var frame ollamaFrame
		if err := json.Unmarshal(line, &frame); err != nil {
			return u, fmt.Errorf("decode frame: %w", err)
		}

		if frame.Message.Content != "" {
			if err := emit(frame.Message.Content); err != nil {
				return u, err
			}
		}

		if frame.Done {
			u = usage{
				PromptTokens:     frame.PromptEvalCount,
				CompletionTokens: frame.EvalCount,
				LatencyMs:        time.Since(start).Milliseconds(),
			}
			break
		}
	}

	if err := scanner.Err(); err != nil {
		return u, fmt.Errorf("read stream: %w", err)
	}
	return u, nil
}
