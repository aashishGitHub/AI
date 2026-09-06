// Agent Console — grounded, streaming LLM backend.
//
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
//
// The retrieval step is what makes answers checkable: every response is
// accompanied by the sources it was grounded in, and the system prompt forbids
// answering beyond them.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	if err := run(log); err != nil {
		log.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	cfg, err := LoadConfig()
	if err != nil {
		return err // fail fast: never boot in a state where every request errors
	}

	// Startup work (embedding the corpus) gets its own bounded context so a
	// hung model server can't leave the process wedged before it ever listens.
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancelStartup()

	srv, err := newServer(startupCtx, cfg, log)
	if err != nil {
		return err
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/api/chat", srv.HandleChat)
	mux.HandleFunc("/healthz", srv.HandleHealth)

	httpServer := &http.Server{
		Addr:    cfg.Addr,
		Handler: withCORS(cfg.AllowedOrigins, mux),
		// ReadHeaderTimeout bounds slowloris-style header stalls. There is
		// deliberately no WriteTimeout: responses are long-lived streams, and a
		// write deadline would sever them mid-answer. Per-request bounding is
		// handled by RequestTimeout inside the handler instead.
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       120 * time.Second,
		ErrorLog:          slog.NewLogLogger(log.Handler(), slog.LevelError),
	}

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

	log.Info("listening",
		"addr", cfg.Addr,
		"provider", cfg.Provider,
		"model", cfg.ChatModel,
		"retrieval", srv.retriever != nil,
		"origins", cfg.AllowedOrigins)

	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}

	<-shutdownDone
	log.Info("stopped cleanly")
	return nil
}

// newServer wires the concrete implementations chosen by config. This is the
// only place that decides *which* provider and *which* retriever exist, which
// is why every other file can be tested with stubs.
func newServer(ctx context.Context, cfg Config, log *slog.Logger) (*Server, error) {
	srv := &Server{cfg: cfg, log: log}

	// No client-level timeout: generation is long-lived by nature, and
	// cancellation is handled per-request via context.
	client := &http.Client{}

	switch cfg.Provider {
	case "fake":
		srv.provider = fakeProvider{}
	default:
		srv.provider = ollamaProvider{baseURL: cfg.OllamaURL, model: cfg.ChatModel, client: client}
	}

	if !cfg.RetrievalEnabled() {
		log.Warn("retrieval disabled: answers will be ungrounded", "reason", "CORPUS_DIR empty")
		return srv, nil
	}

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

	// The fake provider implies "no model server", so embedding would fail too.
	if cfg.Provider == "fake" {
		log.Warn("retrieval skipped with PROVIDER=fake", "chunks", len(chunks))
		return srv, nil
	}

	embedder := ollamaEmbedder{baseURL: cfg.OllamaURL, model: cfg.EmbedModel, client: client}

	start := time.Now()
	retriever, err := NewMemoryRetriever(ctx, embedder, chunks)
	if err != nil {
		return nil, err // embedding configured but broken is a real failure
	}
	srv.retriever = retriever

	log.Info("corpus indexed",
		"dir", cfg.CorpusDir,
		"chunks", len(chunks),
		"embed_model", cfg.EmbedModel,
		"took_ms", time.Since(start).Milliseconds())

	return srv, nil
}
