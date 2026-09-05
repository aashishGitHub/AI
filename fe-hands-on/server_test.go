package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Test doubles
// ---------------------------------------------------------------------------

// stubProvider stands in for a real model. This is the payoff of streamHandler
// taking a provider argument: the transport can be tested with no model server,
// no Docker and no network, so these tests are fast and deterministic.
type stubProvider struct {
	tokens    []string // tokens to emit, in order
	usage     usage    // usage to report on success
	err       error    // if set, fail before emitting anything
	gotPrompt string   // captured: what the handler passed us
}

func (s *stubProvider) Stream(_ context.Context, prompt string, emit func(string) error) (usage, error) {
	s.gotPrompt = prompt
	if s.err != nil {
		return usage{}, s.err
	}
	for _, token := range s.tokens {
		if err := emit(token); err != nil {
			return usage{}, err
		}
	}
	return s.usage, nil
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// parseSSE turns a raw SSE body into the events it carries. Asserting on parsed
// events rather than on a golden string keeps the tests from breaking on
// cosmetic changes like field order.
func parseSSE(t *testing.T, body string) []streamEvent {
	t.Helper()

	var events []streamEvent
	for _, block := range strings.Split(strings.TrimSpace(body), "\n\n") {
		block = strings.TrimSpace(block)
		if block == "" {
			continue
		}
		payload, ok := strings.CutPrefix(block, "data: ")
		if !ok {
			t.Fatalf("SSE block missing %q prefix: %q", "data: ", block)
		}

		var event streamEvent
		if err := json.Unmarshal([]byte(payload), &event); err != nil {
			t.Fatalf("decode SSE payload %q: %v", payload, err)
		}
		events = append(events, event)
	}
	return events
}

// joinTokens concatenates the value of every token event, i.e. the answer the
// browser would have assembled.
func joinTokens(events []streamEvent) string {
	var b strings.Builder
	for _, e := range events {
		if e.Type == "token" {
			b.WriteString(e.Value)
		}
	}
	return b.String()
}

// ---------------------------------------------------------------------------
// streamHandler
// ---------------------------------------------------------------------------

func TestStreamHandlerEmitsTokensThenDone(t *testing.T) {
	stub := &stubProvider{
		tokens: []string{"Hello", ", ", "world"},
		usage:  usage{PromptTokens: 7, CompletionTokens: 3, LatencyMs: 42},
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/stream?q=hi", nil)
	streamHandler(stub)(rec, req)

	if got := rec.Header().Get("Content-Type"); got != "text/event-stream" {
		t.Errorf("Content-Type = %q, want text/event-stream", got)
	}

	events := parseSSE(t, rec.Body.String())

	// Every token must arrive before the terminating done frame; the browser
	// reducer relies on that ordering to know when a turn is finished.
	if len(events) != 4 {
		t.Fatalf("got %d events, want 4 (3 tokens + done): %+v", len(events), events)
	}
	if got := joinTokens(events); got != "Hello, world" {
		t.Errorf("assembled answer = %q, want %q", got, "Hello, world")
	}

	last := events[len(events)-1]
	if last.Type != "done" {
		t.Fatalf("last event type = %q, want done", last.Type)
	}
	if last.Usage == nil {
		t.Fatal("done frame carried no usage; the console cannot show cost/latency without it")
	}
	if last.Usage.CompletionTokens != 3 || last.Usage.LatencyMs != 42 {
		t.Errorf("usage = %+v, want completionTokens=3 latencyMs=42", *last.Usage)
	}
}

func TestStreamHandlerPrompt(t *testing.T) {
	tests := []struct {
		name   string
		target string
		want   string
	}{
		{
			name:   "uses the q query param",
			target: "/stream?q=what+is+SSE",
			want:   "what is SSE",
		},
		{
			// EventSource cannot send a body, so an absent prompt must still
			// produce a valid turn rather than an empty call to the model.
			name:   "falls back to a default when q is absent",
			target: "/stream",
			want:   "In one short paragraph, what are server-sent events?",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			stub := &stubProvider{tokens: []string{"ok"}}

			streamHandler(stub)(httptest.NewRecorder(), httptest.NewRequest(http.MethodGet, tc.target, nil))

			if stub.gotPrompt != tc.want {
				t.Errorf("provider received prompt %q, want %q", stub.gotPrompt, tc.want)
			}
		})
	}
}

func TestStreamHandlerEmitsErrorFrame(t *testing.T) {
	stub := &stubProvider{err: errors.New("model unreachable")}

	rec := httptest.NewRecorder()
	streamHandler(stub)(rec, httptest.NewRequest(http.MethodGet, "/stream?q=hi", nil))

	events := parseSSE(t, rec.Body.String())
	if len(events) != 1 {
		t.Fatalf("got %d events, want 1 error frame: %+v", len(events), events)
	}
	if events[0].Type != "error" {
		t.Errorf("event type = %q, want error", events[0].Type)
	}
	if !strings.Contains(events[0].Value, "model unreachable") {
		t.Errorf("error frame %q does not mention the cause", events[0].Value)
	}
}

func TestStreamHandlerSkipsErrorFrameWhenClientGone(t *testing.T) {
	// When the browser has already hung up there is nobody to receive an error
	// frame, so the handler should stay quiet instead of writing to a dead
	// connection.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	stub := &stubProvider{err: context.Canceled}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/stream?q=hi", nil).WithContext(ctx)
	streamHandler(stub)(rec, req)

	if body := strings.TrimSpace(rec.Body.String()); body != "" {
		t.Errorf("wrote %q to a disconnected client, want nothing", body)
	}
}

// ---------------------------------------------------------------------------
// ollamaProvider — the NDJSON→token adapter, tested against a fake Ollama.
// ---------------------------------------------------------------------------

func TestOllamaProviderTranslatesNDJSON(t *testing.T) {
	// A stand-in for Ollama that replies in its real NDJSON dialect: one JSON
	// object per line, the last carrying done:true plus token counts.
	ollama := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat" {
			t.Errorf("called %q, want /api/chat", r.URL.Path)
		}

		var body struct {
			Model    string `json:"model"`
			Stream   bool   `json:"stream"`
			Messages []struct {
				Role    string `json:"role"`
				Content string `json:"content"`
			} `json:"messages"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if !body.Stream {
			t.Error("stream=false; the provider must ask for a streamed response")
		}
		if len(body.Messages) != 1 || body.Messages[0].Content != "hi" {
			t.Errorf("messages = %+v, want a single user message %q", body.Messages, "hi")
		}

		for _, chunk := range []string{"Hel", "lo"} {
			fmt.Fprintf(w, `{"message":{"content":%q},"done":false}`+"\n", chunk)
		}
		fmt.Fprint(w, `{"message":{"content":""},"done":true,"done_reason":"stop","prompt_eval_count":11,"eval_count":2}`+"\n")
	}))
	defer ollama.Close()

	provider := ollamaProvider{baseURL: ollama.URL, model: "test-model", client: ollama.Client()}

	var got []string
	u, err := provider.Stream(context.Background(), "hi", func(token string) error {
		got = append(got, token)
		return nil
	})
	if err != nil {
		t.Fatalf("Stream() error = %v", err)
	}

	// The empty content on the done frame must not reach the browser as a token.
	if strings.Join(got, "") != "Hello" || len(got) != 2 {
		t.Errorf("tokens = %q, want [\"Hel\" \"lo\"]", got)
	}
	if u.PromptTokens != 11 || u.CompletionTokens != 2 {
		t.Errorf("usage = %+v, want promptTokens=11 completionTokens=2", u)
	}
}

func TestOllamaProviderReportsHTTPFailure(t *testing.T) {
	ollama := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "model not found", http.StatusNotFound)
	}))
	defer ollama.Close()

	provider := ollamaProvider{baseURL: ollama.URL, model: "missing", client: ollama.Client()}

	_, err := provider.Stream(context.Background(), "hi", func(string) error { return nil })
	if err == nil {
		t.Fatal("Stream() error = nil, want a failure for a non-200 response")
	}
	if !strings.Contains(err.Error(), "404") {
		t.Errorf("error %q does not mention the status code", err)
	}
}
