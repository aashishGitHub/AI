package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Wire contract — the frontend codes against this, not against any model.
// ---------------------------------------------------------------------------

type streamEvent struct {
	Type    string   `json:"type"`              // "sources" | "token" | "done" | "error"
	Value   string   `json:"value,omitempty"`   // token text, or error message
	Sources []Source `json:"sources,omitempty"` // only on the "sources" frame
	Usage   *usage   `json:"usage,omitempty"`   // only on the "done" frame
}

// Source is a citation. Sent before any token so the UI can show what the
// answer is grounded in while it is still being written — and so a user can
// judge the answer against its evidence rather than trusting it.
type Source struct {
	ID    string `json:"id"`
	DocID string `json:"docId"`
	Title string `json:"title"`
	Text  string `json:"text"`
}

type chatRequest struct {
	Messages []Message `json:"messages"`
}

const (
	maxRequestBytes  = 1 << 20 // 1 MiB: a conversation, not a file upload
	maxMessages      = 40      // bound history growth
	maxMessageLength = 8000
)

// Validate rejects malformed input before any model is called, so a bad request
// costs nothing. Every limit here exists because the alternative is unbounded.
func (r chatRequest) Validate() error {
	switch {
	case len(r.Messages) == 0:
		return errors.New("messages must not be empty")
	case len(r.Messages) > maxMessages:
		return fmt.Errorf("too many messages: %d (max %d)", len(r.Messages), maxMessages)
	}

	for i, m := range r.Messages {
		switch m.Role {
		case "user", "assistant":
		default:
			// "system" is rejected on purpose: the server owns the system
			// prompt. Accepting one from the client is a prompt-injection hole.
			return fmt.Errorf("messages[%d].role must be \"user\" or \"assistant\", got %q", i, m.Role)
		}
		if strings.TrimSpace(m.Content) == "" {
			return fmt.Errorf("messages[%d].content must not be empty", i)
		}
		if len(m.Content) > maxMessageLength {
			return fmt.Errorf("messages[%d].content exceeds %d characters", i, maxMessageLength)
		}
	}

	if last := r.Messages[len(r.Messages)-1]; last.Role != "user" {
		return errors.New("the last message must have role \"user\"")
	}
	return nil
}

// ---------------------------------------------------------------------------
// Grounding
// ---------------------------------------------------------------------------

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

// ungroundedSystemPrompt is used when no corpus is configured. It is honest
// about the absence of grounding rather than pretending to be authoritative.
const ungroundedSystemPrompt = `You are a helpful assistant. No documentation corpus is configured, so answer from general knowledge and say clearly when you are unsure.`

// buildMessages assembles what the model actually sees: a server-owned system
// prompt, then the conversation. Client-supplied system messages are rejected
// during validation, so this prompt cannot be overridden from the browser.
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

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

// Server holds the request-scoped collaborators. Both are interfaces, so tests
// inject stubs and run the whole handler with no model and no network.
type Server struct {
	cfg       Config
	provider  provider
	retriever Retriever // nil when retrieval is disabled
	log       *slog.Logger
}

func writeEvent(w http.ResponseWriter, flusher http.Flusher, event streamEvent) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	// SSE framing: "data: <payload>\n\n"; the blank line terminates the event.
	if _, err := fmt.Fprintf(w, "data: %s\n\n", payload); err != nil {
		return err
	}
	// Without an explicit flush the bytes sit in Go's buffer until the handler
	// returns, which would defeat streaming entirely.
	flusher.Flush()
	return nil
}

// HandleChat streams an answer for a conversation.
//
// POST rather than GET-with-EventSource: EventSource cannot send a body, so it
// cannot carry conversation history, and it cannot be aborted cleanly. fetch +
// ReadableStream on the client costs a few more lines and removes both limits.
func (s *Server) HandleChat(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req chatRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBytes)).Decode(&req); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}
	if err := req.Validate(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}

	// Bound the whole generation. Without this a wedged upstream holds the
	// connection, and its goroutine, indefinitely.
	ctx, cancel := context.WithTimeout(r.Context(), s.cfg.RequestTimeout)
	defer cancel()

	question := req.Messages[len(req.Messages)-1].Content
	log := s.log.With("question_chars", len(question), "turns", len(req.Messages))

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no") // stop proxies buffering the stream
	w.WriteHeader(http.StatusOK)

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

	// --- generate -----------------------------------------------------------
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

	log.Info("chat completed",
		"prompt_tokens", u.PromptTokens,
		"completion_tokens", u.CompletionTokens,
		"latency_ms", u.LatencyMs)

	writeEvent(w, flusher, streamEvent{Type: "done", Usage: &u})
}

// HandleHealth reports readiness. It deliberately reports *dependency* health,
// not just process liveness: a server that is up but cannot reach its model is
// not ready, and saying "ok" would hide the outage from whatever is watching.
func (s *Server) HandleHealth(w http.ResponseWriter, r *http.Request) {
	status := map[string]any{
		"status":    "ok",
		"provider":  s.cfg.Provider,
		"model":     s.cfg.ChatModel,
		"retrieval": s.retriever != nil,
	}
	if r, ok := s.retriever.(*memoryRetriever); ok && r != nil {
		status["chunks"] = r.Len()
	}

	code := http.StatusOK
	if s.cfg.Provider == "ollama" {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, s.cfg.OllamaURL+"/api/tags", nil)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			status["status"], status["error"] = "degraded", err.Error()
			code = http.StatusServiceUnavailable
		} else {
			resp.Body.Close()
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(status)
}

// withCORS applies an origin allowlist. The previous "*" was fine for a local
// demo and wrong for anything else: it lets any page on the internet call this
// API with the user's browser.
func withCORS(allowed []string, next http.Handler) http.Handler {
	set := make(map[string]bool, len(allowed))
	for _, o := range allowed {
		set[strings.TrimSpace(o)] = true
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if set["*"] {
			w.Header().Set("Access-Control-Allow-Origin", "*")
		} else if origin != "" && set[origin] {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Add("Vary", "Origin") // the response differs per origin
		}
		w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
