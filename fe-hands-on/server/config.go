package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config is resolved once at startup and never mutated. Everything the server
// needs comes from here, so behaviour is inspectable from the environment
// rather than scattered through the code as literals.
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

func LoadConfig() (Config, error) {
	c := Config{
		Addr:           env("ADDR", ":8080"),
		Provider:       env("PROVIDER", "ollama"),
		OllamaURL:      env("OLLAMA_URL", "http://localhost:11434"),
		ChatModel:      env("OLLAMA_MODEL", "llama3.2:1b"),
		EmbedModel:     env("EMBED_MODEL", "nomic-embed-text"),
		CorpusDir:      env("CORPUS_DIR", "corpus"),
		AllowedOrigins: strings.Split(env("ALLOWED_ORIGINS", "http://localhost:3000"), ","),
	}

	var err error
	if c.TopK, err = envInt("TOP_K", 4); err != nil {
		return c, err
	}
	if c.RequestTimeout, err = envDuration("REQUEST_TIMEOUT", 120*time.Second); err != nil {
		return c, err
	}
	if c.ShutdownGrace, err = envDuration("SHUTDOWN_GRACE", 10*time.Second); err != nil {
		return c, err
	}

	return c, c.Validate()
}

// Validate fails fast at startup. A misconfigured server that boots and then
// errors on every request is strictly worse than one that refuses to start.
func (c Config) Validate() error {
	switch c.Provider {
	case "ollama", "fake":
	default:
		return fmt.Errorf("PROVIDER must be \"ollama\" or \"fake\", got %q", c.Provider)
	}

	if c.TopK < 1 {
		return fmt.Errorf("TOP_K must be >= 1, got %d", c.TopK)
	}
	if c.Provider == "ollama" && c.OllamaURL == "" {
		return fmt.Errorf("OLLAMA_URL must be set when PROVIDER=ollama")
	}
	for _, o := range c.AllowedOrigins {
		if strings.TrimSpace(o) == "" {
			return fmt.Errorf("ALLOWED_ORIGINS contains an empty entry: %q", c.AllowedOrigins)
		}
	}
	return nil
}

// RetrievalEnabled reports whether the server should ground answers in a corpus.
// With no corpus the console still works — it just answers ungrounded, which is
// the behaviour the eval suite exists to catch.
func (c Config) RetrievalEnabled() bool { return c.CorpusDir != "" }

func env(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) (int, error) {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return fallback, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer: %w", key, err)
	}
	return n, nil
}

func envDuration(key string, fallback time.Duration) (time.Duration, error) {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return fallback, nil
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return 0, fmt.Errorf("%s must be a duration such as 30s: %w", key, err)
	}
	return d, nil
}
