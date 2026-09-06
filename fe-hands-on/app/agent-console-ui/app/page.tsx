"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { streamChat, type Source } from "./lib/chat";
import { initialState, reducer, toMessages, type Turn } from "./lib/reducer";

export default function Home() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [input, setInput] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Abort any in-flight request when the component goes away, so navigating
  // off the page stops the model generating rather than leaking the stream.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Follow the answer as it streams. `block: "end"` avoids yanking the whole
  // page when the transcript is short.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns, state.status]);

  const run = useCallback(async (messages: ReturnType<typeof toMessages>) => {
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamChat(messages, controller.signal)) {
        dispatch(event);
      }
    } catch (err) {
      // An abort is a user action, not a failure — the reducer already
      // recorded it, so don't overwrite that with an error banner.
      if (controller.signal.aborted) return;
      dispatch({
        type: "error",
        value: err instanceof Error ? err.message : "the stream failed",
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  function ask(question: string) {
    dispatch({ type: "ask", question });
    void run([...toMessages(state.turns), { role: "user", content: question }]);
  }

  function retry() {
    const last = state.turns[state.turns.length - 1];
    if (!last) return;
    dispatch({ type: "retry" });
    void run([...toMessages(state.turns.slice(0, -1)), { role: "user", content: last.question }]);
  }

  function stop() {
    abortRef.current?.abort();
    dispatch({ type: "abort" });
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || state.status === "streaming") return;
    setInput("");
    ask(question);
  }

  const streaming = state.status === "streaming";

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 font-sans text-zinc-900 dark:bg-black dark:text-zinc-100">
      <header className="border-b border-zinc-200 px-6 py-3 dark:border-zinc-800">
        <h1 className="text-sm font-semibold">Agent Console</h1>
        <p className="text-xs text-zinc-500">Grounded in the local documentation corpus</p>
      </header>

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6">
        {state.turns.length === 0 && (
          <div className="text-sm text-zinc-500">
            <p className="mb-2">Ask about the indexed documentation. Try:</p>
            <ul className="list-inside list-disc space-y-1">
              <li>How do I create a primary index in Capella?</li>
              <li>What is the difference between a scope and a collection?</li>
            </ul>
          </div>
        )}

        {state.turns.map((turn, i) => (
          <TurnView key={i} turn={turn} streaming={streaming && i === state.turns.length - 1} onRetry={retry} />
        ))}

        <div ref={bottomRef} />
      </main>

      <form
        onSubmit={onSubmit}
        className="sticky bottom-0 border-t border-zinc-200 bg-zinc-50/90 backdrop-blur dark:border-zinc-800 dark:bg-black/90"
      >
        <div className="mx-auto flex w-full max-w-3xl gap-2 px-4 py-3 sm:px-6">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the documentation…"
            autoComplete="off"
            disabled={streaming}
            className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2 outline-none focus:border-zinc-500 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
          />
          {streaming ? (
            // Stop is only reachable while streaming, which is the only time
            // it means anything — and it aborts the request rather than just
            // hiding the output.
            <button
              type="button"
              onClick={stop}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={input.trim() === ""}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function TurnView({
  turn,
  streaming,
  onRetry,
}: {
  turn: Turn;
  streaming: boolean;
  onRetry: () => void;
}) {
  return (
    <article className="flex flex-col gap-3">
      <p className="self-end rounded-2xl bg-zinc-200 px-4 py-2 text-sm dark:bg-zinc-800">{turn.question}</p>

      {turn.sources.length > 0 && <Sources sources={turn.sources} />}

      <div className="rounded-2xl bg-white p-4 dark:bg-zinc-900">
        {turn.answer === "" && streaming ? (
          <p className="text-sm text-zinc-500" role="status">
            Searching the documentation…
          </p>
        ) : (
          // The model emits Markdown — fenced code, lists, tables. Rendering it
          // as plain text made every code block unreadable. react-markdown does
          // not pass raw HTML through, so model output cannot inject markup.
          <div className="prose-sm max-w-none [&_code]:rounded [&_code]:bg-zinc-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em] [&_h1]:mt-4 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:text-sm [&_h2]:font-semibold [&_li]:my-0.5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-zinc-100 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_table]:my-2 [&_table]:block [&_table]:overflow-x-auto [&_td]:border [&_td]:border-zinc-200 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-zinc-200 [&_th]:px-2 [&_th]:py-1 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 dark:[&_code]:bg-zinc-800 dark:[&_pre]:bg-zinc-950 dark:[&_td]:border-zinc-800 dark:[&_th]:border-zinc-800">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer}</ReactMarkdown>
            {streaming && (
              <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-current align-middle" />
            )}
          </div>
        )}

        {turn.aborted && <p className="mt-2 text-xs text-zinc-500">Stopped.</p>}

        {turn.error && (
          <div className="mt-3 flex items-center gap-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            <span className="flex-1">{turn.error}</span>
            <button
              type="button"
              onClick={onRetry}
              className="rounded border border-red-300 px-2 py-1 text-xs font-medium hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-900/40"
            >
              Retry
            </button>
          </div>
        )}

        {turn.usage && (
          // Cost and latency per turn, in the UI rather than only in a log —
          // the trade-off stays visible while iterating on prompts.
          <p className="mt-3 border-t border-zinc-200 pt-2 font-mono text-xs text-zinc-500 dark:border-zinc-800">
            {turn.usage.promptTokens} prompt + {turn.usage.completionTokens} completion tokens ·{" "}
            {turn.usage.latencyMs}ms
          </p>
        )}
      </div>
    </article>
  );
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <details className="rounded-lg border border-zinc-200 bg-white text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {sources.length} source{sources.length === 1 ? "" : "s"} — the answer is grounded in these
      </summary>
      <ol className="space-y-2 border-t border-zinc-200 px-3 py-2 dark:border-zinc-800">
        {sources.map((source, i) => (
          <li key={source.id} className="text-xs">
            {/* Numbered to match the [n] citations the model is told to use. */}
            <span className="font-mono text-zinc-500">[{i + 1}]</span>{" "}
            <span className="font-medium">{source.title}</span>{" "}
            <span className="text-zinc-500">({source.docId})</span>
            <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
              {source.text}
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}
