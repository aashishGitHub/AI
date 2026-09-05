"use client";
import { useEffect, useReducer, useRef, useState } from "react";

// The wire contract from fe-hands-on/server.go. The UI codes against this
// shape, not against any particular model — swapping Ollama for Bedrock on the
// backend changes nothing in here.
type Usage = {
  promptTokens: number;
  completionTokens: number;
  latencyMs: number;
};

type StreamEvent =
  | { type: "token"; value: string }
  | { type: "done"; usage?: Usage }
  | { type: "error"; value: string };

type Turn = {
  prompt: string;
  answer: string;
  usage?: Usage;
  error?: string;
};

type Action = StreamEvent | { type: "ask"; prompt: string };

type State = {
  status: "idle" | "streaming";
  prompt: string; // prompt of the in-flight turn
  current: string; // tokens accumulated so far for the in-flight turn
  history: Turn[];
};

const initialState: State = {
  status: "idle",
  prompt: "",
  current: "",
  history: [],
};

// A reducer (rather than several useStates) because a streaming turn is a small
// state machine: idle → streaming → idle, and every transition touches more than
// one field at once. Keeping those moves in one place is what stops the "tokens
// arrive after done" class of bug.
function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ask":
      return { status: "streaming", prompt: action.prompt, current: "", history: state.history };

    case "token":
      return { ...state, current: state.current + action.value };

    case "done":
      return {
        status: "idle",
        prompt: "",
        current: "",
        history: [
          ...state.history,
          { prompt: state.prompt, answer: state.current, usage: action.usage },
        ],
      };

    case "error":
      return {
        status: "idle",
        prompt: "",
        current: "",
        history: [
          ...state.history,
          { prompt: state.prompt, answer: state.current, error: action.value },
        ],
      };
  }
}

export default function Home() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [input, setInput] = useState("");
  const sourceRef = useRef<EventSource | null>(null);

  // Close any open stream when the component unmounts, otherwise a navigation
  // away leaves the connection (and the model generating) alive.
  useEffect(() => {
    return () => sourceRef.current?.close();
  }, []);

  function ask(prompt: string) {
    sourceRef.current?.close(); // supersede any in-flight turn

    dispatch({ type: "ask", prompt });

    // EventSource is GET-only with no body, which is why the prompt travels as
    // a query param. Moving to multi-turn history later means switching to
    // POST + fetch/ReadableStream — the reducer above would not change.
    const source = new EventSource(
      `http://localhost:8080/stream?q=${encodeURIComponent(prompt)}`,
    );
    sourceRef.current = source;

    source.onmessage = (e) => {
      const event: StreamEvent = JSON.parse(e.data);
      dispatch(event);

      // The server closes the stream after "done", and EventSource would then
      // auto-reconnect and replay the whole answer on a loop. Close it first.
      if (event.type === "done" || event.type === "error") source.close();
    };

    source.onerror = () => {
      dispatch({ type: "error", value: "Stream failed — is the Go server on :8080 running?" });
      source.close();
    };
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const prompt = input.trim();
    if (!prompt || state.status === "streaming") return;
    setInput("");
    ask(prompt);
  }

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-3xl flex-1 flex-col gap-4 px-6 py-16 sm:px-16">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Agent Console</h1>

        {state.history.length === 0 && state.status === "idle" && (
          <p className="text-zinc-500">Ask something to start a stream.</p>
        )}

        {state.history.map((turn, i) => (
          <div key={i} className="flex flex-col gap-2">
            <p className="self-end rounded-lg bg-zinc-200 px-4 py-2 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
              {turn.prompt}
            </p>

            <div className="rounded-lg bg-white p-4 dark:bg-zinc-900">
              <p className="whitespace-pre-wrap">{turn.answer}</p>

              {turn.error && <p className="mt-2 text-sm text-red-600">{turn.error}</p>}

              {/* Real cost/latency per turn — the seed of the observability
                  dashboard. Surfacing it in the UI keeps the trade-off visible
                  while iterating on prompts. */}
              {turn.usage && (
                <p className="mt-3 border-t border-zinc-200 pt-2 font-mono text-xs text-zinc-500 dark:border-zinc-800">
                  {turn.usage.promptTokens} prompt + {turn.usage.completionTokens} completion tokens ·{" "}
                  {turn.usage.latencyMs}ms
                </p>
              )}
            </div>
          </div>
        ))}

        {state.status === "streaming" && (
          <div className="flex flex-col gap-2">
            <p className="self-end rounded-lg bg-zinc-200 px-4 py-2 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
              {state.prompt}
            </p>
            <p className="whitespace-pre-wrap rounded-lg bg-white p-4 dark:bg-zinc-900">
              {state.current}
              <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-current align-middle" />
            </p>
          </div>
        )}

        <form onSubmit={onSubmit} className="sticky bottom-4 mt-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the agent…"
            className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <button
            type="submit"
            disabled={state.status === "streaming" || input.trim() === ""}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {state.status === "streaming" ? "Streaming…" : "Send"}
          </button>
        </form>
      </main>
    </div>
  );
}
