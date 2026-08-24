package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type streamEvent struct {
	Type  string `json:"type"`
	Value string `json:"value,omitempty"`
}

const fakeResponse = "Server-sent events let the server push tokens to the browser over a single long-lived HTTP connection."

func writeEvent(w http.ResponseWriter, flusher http.Flusher, event streamEvent) error {
	payload, err := json.Marshal(event)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintf(w, "data: %s\n\n", payload); err != nil {
		return err
	}
	flusher.Flush()
	return nil
}

func streamHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	for _, word := range strings.Fields(fakeResponse) {
		select {
		case <-r.Context().Done():
			return
		case <-time.After(120 * time.Millisecond):
		}

		if err := writeEvent(w, flusher, streamEvent{Type: "token", Value: word + " "}); err != nil {
			return
		}
	}

	writeEvent(w, flusher, streamEvent{Type: "done"})
}

func main() {
	http.HandleFunc("/stream", streamHandler)
	http.ListenAndServe(":8080", nil)
}
