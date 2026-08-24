"use client";
import { useEffect, useReducer } from "react";

type StreamEvent =
  | { type: "token"; value: string }
  | { type: "done" };

type State = {
  status: "idle" | "streaming";
  current: string;
  history: string[];
};

const initialState: State = { status: "idle", current: "", history: [] };

function reducer(state: State, event: StreamEvent): State {
  switch (event.type) {
    case "token":
      return { ...state, status: "streaming", current: state.current + event.value };
    case "done":
      return {
        status: "idle",
        current: "",
        history: [...state.history, state.current],
      };
  }
}

export default function Home() {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    const es = new EventSource("http://localhost:8080/stream");

    es.onmessage = (e) => {
      const event: StreamEvent = JSON.parse(e.data);
      dispatch(event);
      // EventSource auto-reconnects when the server closes the stream, which would
      // replay the whole response into history on a loop. Close it ourselves instead.
      if (event.type === "done") es.close();
    };

    es.onerror = () => es.close();

    return () => es.close();
  }, []);

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-3xl flex-1 flex-col gap-4 px-16 py-32">
        {state.history.map((message, i) => (
          <p key={i} className="rounded-lg bg-white p-4 dark:bg-zinc-900">
            {message}
          </p>
        ))}

        {state.status === "streaming" && (
          <p className="rounded-lg bg-white p-4 dark:bg-zinc-900">
            {state.current}
            <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-current align-middle" />
          </p>
        )}

        {state.status === "idle" && state.history.length === 0 && (
          <p className="text-zinc-500">Waiting for server-sent events...</p>
        )}
      </main>
    </div>
  );
}
