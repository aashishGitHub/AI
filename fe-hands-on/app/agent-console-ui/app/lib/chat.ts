// Transport for the Agent Console stream.
//
// Kept out of the component so the wire format has one owner and can be tested
// without rendering anything. React should be handed events, not parsing.

export type Usage = {
  promptTokens: number;
  completionTokens: number;
  latencyMs: number;
};

export type Source = {
  id: string;
  docId: string;
  title: string;
  text: string;
};

/** Mirrors streamEvent in server/stream.go. */
export type StreamEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; value: string }
  | { type: "done"; usage?: Usage }
  | { type: "error"; value: string };

export type Message = {
  role: "user" | "assistant";
  content: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

/**
 * Splits a byte stream into SSE events.
 *
 * A network chunk is not an SSE event: one read can contain half an event, or
 * three of them. Buffering until the "\n\n" terminator is what makes the parse
 * correct rather than usually-correct — and a token split across two reads is
 * exactly the bug that only shows up under load.
 */
export async function* parseSSE(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);

        if (!block.startsWith("data: ")) continue;
        try {
          yield JSON.parse(block.slice(6)) as StreamEvent;
        } catch {
          // A malformed frame should not kill an otherwise healthy stream.
          continue;
        }
      }

      if (signal?.aborted) break;
    }
  } finally {
    // Releasing the lock lets the underlying connection be torn down when the
    // caller aborts mid-answer, instead of leaking it.
    reader.releaseLock();
  }
}

/**
 * POSTs a conversation and yields events as they arrive.
 *
 * POST rather than EventSource: EventSource is GET-only with no body, so it
 * cannot carry multi-turn history, and it cannot be cancelled cleanly. Those
 * are the two things this console needs most.
 */
export async function* streamChat(
  messages: Message[],
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });

  if (!response.ok) {
    // 4xx/5xx come back as plain text, not SSE — surface the server's reason
    // rather than a generic failure.
    const detail = (await response.text()).trim();
    throw new Error(detail || `request failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("response had no body to stream");
  }

  yield* parseSSE(response.body, signal);
}
