// Agent Console — SSE token-streaming backend.
//
// ARCHITECTURE
//
//	browser ──EventSource(GET /stream?q=)──▶ streamHandler ──▶ provider ──▶ LLM
//	        ◀──── SSE frames: {token}* {done} ────┘
//
// The design goal (from docs/instructions.md) is that "models can be updated or
// replaced without significant downtime". Two seams make that possible:
//
//  1. The SSE wire contract (streamEvent) is the stable interface the frontend
//     codes against. It says nothing about which model produced the tokens.
//  2. The provider interface is the swap point. Ollama today, Bedrock later —
//     streamHandler never changes, and neither does the frontend.
//
// This is the "stateless inference plane" idea: the transport layer holds no
// model-specific state, so swapping the model behind it is a config change,
// not a rewrite.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Wire contract — the frontend's reducer switches on `type`. Do not break this
// shape without changing app/agent-console-ui/app/page.tsx in the same commit.
// ---------------------------------------------------------------------------

type streamEvent struct {
	Type  string `json:"type"`            // "token" | "done" | "error"
	Value string `json:"value,omitempty"` // token text, or error message
	Usage *usage `json:"usage,omitempty"` // present only on the final "done" frame
}

// usage rides along on the done frame so the console can display real cost and
// latency per request. This is the seed of the observability dashboard: you
// cannot tune what you do not measure, and token counts are the unit of cost.
type usage struct {
	PromptTokens     int   `json:"promptTokens"`
	CompletionTokens int   `json:"completionTokens"`
	LatencyMs        int64 `json:"latencyMs"`
}

// ---------------------------------------------------------------------------
// Provider — the swap seam.
// ---------------------------------------------------------------------------

// provider turns a prompt into a stream of tokens. Implementations push each
// token through emit as soon as it arrives; they must not buffer the whole
// response, because time-to-first-token is what makes streaming worth doing.
//
// ctx carries client disconnection. Implementations must honour it so that a
// user closing the tab stops the upstream generation instead of paying for
// tokens nobody will read.
type provider interface {
	Stream(ctx context.Context, prompt string, emit func(token string) error) (usage, error)
}

// fakeProvider replays a canned sentence word by word. It keeps the frontend
// and the SSE plumbing developable with no model server running, and it makes
// transport-level tests deterministic — the same reason evals prefer a
// deterministic assertion before an LLM-graded one.
type fakeProvider struct{}

const fakeResponse = "Server-sent events let the server push tokens to the browser over a single long-lived HTTP connection."

func (fakeProvider) Stream(ctx context.Context, _ string, emit func(string) error) (usage, error) {
	start := time.Now()
	words := strings.Fields(fakeResponse)

	for _, word := range words {
		select {
		case <-ctx.Done(): // client went away
			return usage{}, ctx.Err()
		case <-time.After(120 * time.Millisecond): // simulate generation pace
		}
		if err := emit(word + " "); err != nil {
			return usage{}, err
		}
	}

	return usage{CompletionTokens: len(words), LatencyMs: time.Since(start).Milliseconds()}, nil
}

// ollamaProvider streams from a local Ollama server.
//
// Ollama's /api/chat with stream:true returns NDJSON — one JSON object per
// line — rather than SSE. Translating that into our SSE contract is exactly
// the adapter work a provider is meant to encapsulate: every vendor has a
// different streaming dialect, and none of it should leak to the frontend.
type ollamaProvider struct {
	baseURL string
	model   string
	client  *http.Client
}

// ollamaFrame is one NDJSON line from /api/chat. The final frame carries
// done:true plus the token counts for the whole request.
type ollamaFrame struct {
	Message struct {
		Content string `json:"content"`
	} `json:"message"`
	Done            bool   `json:"done"`
	DoneReason      string `json:"done_reason"`
	PromptEvalCount int    `json:"prompt_eval_count"` // prompt tokens
	EvalCount       int    `json:"eval_count"`        // completion tokens
}

func (o ollamaProvider) Stream(ctx context.Context, prompt string, emit func(string) error) (usage, error) {
	start := time.Now()

	body, err := json.Marshal(map[string]any{
		"model":    o.model,
		"messages": []map[string]string{{"role": "user", "content": prompt}},
		"stream":   true,
	})
	if err != nil {
		return usage{}, fmt.Errorf("encode request: %w", err)
	}

	// NewRequestWithContext is what propagates client disconnection upstream:
	// cancelling ctx aborts the in-flight generation.
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, o.baseURL+"/api/chat", strings.NewReader(string(body)))
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
	// Scanner is fine here: NDJSON frames are one small object per line.
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

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

func writeEvent(w http.ResponseWriter, flusher http.Flusher, event streamEvent) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	// SSE framing: "data: <payload>\n\n". The blank line terminates the event.
	if _, err := fmt.Fprintf(w, "data: %s\n\n", payload); err != nil {
		return err
	}
	// Without an explicit flush the response sits in Go's buffer and the client
	// sees nothing until the handler returns — which would defeat streaming.
	flusher.Flush()
	return nil
}

// streamHandler takes its provider as an argument rather than reaching for a
// global. That is what makes it testable: a test injects a stub provider and
// asserts on the SSE frames, with no model server involved.
func streamHandler(p provider) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("Access-Control-Allow-Origin", "*")

		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
			return
		}

		// EventSource can only issue GET with no body, so the prompt arrives as
		// a query param. A production console would move to POST + fetch with a
		// ReadableStream to carry conversation history; ?q= keeps the Wk1
		// skeleton honest without rewriting the frontend transport yet.
		prompt := r.URL.Query().Get("q")
		if prompt == "" {
			prompt = "In one short paragraph, what are server-sent events?"
		}

		emit := func(token string) error {
			return writeEvent(w, flusher, streamEvent{Type: "token", Value: token})
		}

		u, err := p.Stream(r.Context(), prompt, emit)
		if err != nil {
			// A cancelled context means the client hung up; there is nobody left
			// to send an error frame to, so just log it and return.
			if r.Context().Err() != nil {
				log.Printf("client disconnected: %v", err)
				return
			}
			log.Printf("stream failed: %v", err)
			writeEvent(w, flusher, streamEvent{Type: "error", Value: err.Error()})
			return
		}

		log.Printf("prompt=%q promptTokens=%d completionTokens=%d latencyMs=%d",
			prompt, u.PromptTokens, u.CompletionTokens, u.LatencyMs)

		writeEvent(w, flusher, streamEvent{Type: "done", Usage: &u})
	}
}

// newProvider picks the backend from the environment. Swapping models is a
// restart with a different env var, not a code change — the point of the
// provider seam.
func newProvider() provider {
	if os.Getenv("PROVIDER") == "fake" {
		log.Println("provider=fake (no LLM)")
		return fakeProvider{}
	}

	baseURL := os.Getenv("OLLAMA_URL")
	if baseURL == "" {
		baseURL = "http://localhost:11434"
	}
	model := os.Getenv("OLLAMA_MODEL")
	if model == "" {
		model = "llama3.2:1b"
	}

	log.Printf("provider=ollama model=%s url=%s", model, baseURL)
	return ollamaProvider{
		baseURL: baseURL,
		model:   model,
		// No client-side timeout: generation is long-lived by nature and
		// cancellation is handled per-request via the request context.
		client: &http.Client{},
	}
}

func main() {
	http.HandleFunc("/stream", streamHandler(newProvider()))

	log.Println("listening on :8080")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatal(err)
	}
}
