import { test } from "node:test";
import assert from "node:assert/strict";

import { parseSSE, type StreamEvent } from "./chat.ts";

/** Builds a ReadableStream from raw chunks, so we control exactly where the
 *  network "splits" the bytes. That split point is the whole point of these
 *  tests: a chunk is not an event. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const e of parseSSE(streamOf(chunks))) events.push(e);
  return events;
}

const frame = (o: unknown) => `data: ${JSON.stringify(o)}\n\n`;

test("parses whole events", async () => {
  const events = await collect([
    frame({ type: "token", value: "a" }),
    frame({ type: "done", usage: { promptTokens: 1, completionTokens: 2, latencyMs: 3 } }),
  ]);

  assert.equal(events.length, 2);
  assert.deepEqual(events[0], { type: "token", value: "a" });
  assert.equal(events[1].type, "done");
});

test("reassembles an event split across network chunks", async () => {
  // The bug that only appears under load: one read containing half an event.
  const whole = frame({ type: "token", value: "hello" });
  const events = await collect([whole.slice(0, 12), whole.slice(12)]);

  assert.equal(events.length, 1);
  assert.deepEqual(events[0], { type: "token", value: "hello" });
});

test("handles several events arriving in one chunk", async () => {
  const events = await collect([
    frame({ type: "token", value: "a" }) + frame({ type: "token", value: "b" }) + frame({ type: "done" }),
  ]);

  assert.equal(events.length, 3);
  assert.deepEqual(
    events.filter((e) => e.type === "token").map((e) => (e as { value: string }).value),
    ["a", "b"],
  );
});

test("splits multi-byte UTF-8 correctly across chunk boundaries", async () => {
  // "→" is 3 bytes; cutting mid-character must not corrupt it.
  const bytes = new TextEncoder().encode(frame({ type: "token", value: "a→b" }));
  const events: StreamEvent[] = [];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes.slice(0, 20));
      controller.enqueue(bytes.slice(20));
      controller.close();
    },
  });
  for await (const e of parseSSE(stream)) events.push(e);

  assert.deepEqual(events[0], { type: "token", value: "a→b" });
});

test("skips a malformed frame without killing the stream", async () => {
  const events = await collect([
    "data: {not json\n\n",
    frame({ type: "token", value: "survived" }),
  ]);

  assert.equal(events.length, 1);
  assert.deepEqual(events[0], { type: "token", value: "survived" });
});

test("ignores non-data lines such as SSE comments", async () => {
  const events = await collect([": keep-alive\n\n", frame({ type: "done" })]);

  assert.equal(events.length, 1);
  assert.equal(events[0].type, "done");
});

test("yields nothing for an empty stream", async () => {
  assert.deepEqual(await collect([]), []);
});
