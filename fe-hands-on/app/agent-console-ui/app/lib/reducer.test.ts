import { test } from "node:test";
import assert from "node:assert/strict";

import { initialState, reducer, toMessages, type Action, type State } from "./reducer.ts";

/** Applies a sequence of actions, the way a real stream would. */
function run(actions: Action[], from: State = initialState): State {
  return actions.reduce(reducer, from);
}

const askHello: Action = { type: "ask", question: "hello?" };

test("ask opens a streaming turn", () => {
  const state = run([askHello]);

  assert.equal(state.status, "streaming");
  assert.equal(state.turns.length, 1);
  assert.equal(state.turns[0].question, "hello?");
  assert.equal(state.turns[0].answer, "");
});

test("tokens accumulate onto the open turn", () => {
  const state = run([
    askHello,
    { type: "token", value: "Hel" },
    { type: "token", value: "lo" },
  ]);

  assert.equal(state.turns[0].answer, "Hello");
  assert.equal(state.status, "streaming", "still streaming until done arrives");
});

test("sources attach before any token and survive them", () => {
  const sources = [{ id: "c1", docId: "indexes.md", title: "Primary indexes", text: "..." }];
  const state = run([askHello, { type: "sources", sources }, { type: "token", value: "x" }]);

  assert.deepEqual(state.turns[0].sources, sources);
  assert.equal(state.turns[0].answer, "x");
});

test("done ends the turn and records usage", () => {
  const usage = { promptTokens: 10, completionTokens: 3, latencyMs: 42 };
  const state = run([askHello, { type: "token", value: "hi" }, { type: "done", usage }]);

  assert.equal(state.status, "idle");
  assert.deepEqual(state.turns[0].usage, usage);
});

test("error ends the turn and keeps the partial answer", () => {
  const state = run([
    askHello,
    { type: "token", value: "partial" },
    { type: "error", value: "model unreachable" },
  ]);

  assert.equal(state.status, "idle");
  assert.equal(state.turns[0].error, "model unreachable");
  assert.equal(state.turns[0].answer, "partial", "a partial answer is still worth reading");
});

test("abort keeps what already streamed", () => {
  const state = run([askHello, { type: "token", value: "half an ans" }, { type: "abort" }]);

  assert.equal(state.status, "idle");
  assert.equal(state.turns[0].aborted, true);
  assert.equal(state.turns[0].answer, "half an ans", "deleting it would feel like a crash");
});

test("retry replaces the failed turn rather than appending one", () => {
  const failed = run([askHello, { type: "error", value: "boom" }]);
  const state = reducer(failed, { type: "retry" });

  assert.equal(state.turns.length, 1, "no dead entry left in the transcript");
  assert.equal(state.turns[0].question, "hello?");
  assert.equal(state.turns[0].answer, "");
  assert.equal(state.turns[0].error, undefined);
  assert.equal(state.status, "streaming");
});

test("a second ask appends a turn and keeps the first", () => {
  const first = run([askHello, { type: "token", value: "hi" }, { type: "done" }]);
  const state = reducer(first, { type: "ask", question: "again?" });

  assert.equal(state.turns.length, 2);
  assert.equal(state.turns[0].answer, "hi");
  assert.equal(state.turns[1].question, "again?");
});

test("events with no open turn are ignored rather than throwing", () => {
  assert.doesNotThrow(() => reducer(initialState, { type: "token", value: "orphan" }));
  assert.deepEqual(reducer(initialState, { type: "token", value: "orphan" }).turns, []);
});

// ---------------------------------------------------------------------------
// History sent back to the model
// ---------------------------------------------------------------------------

test("toMessages pairs completed turns and ends on the new question", () => {
  const state = run([
    askHello,
    { type: "token", value: "first answer" },
    { type: "done" },
    { type: "ask", question: "follow up?" },
  ]);

  assert.deepEqual(toMessages(state.turns), [
    { role: "user", content: "hello?" },
    { role: "assistant", content: "first answer" },
    { role: "user", content: "follow up?" },
  ]);
});

test("toMessages excludes a failed answer from history", () => {
  // Replaying a failed turn as real assistant output poisons the next turn.
  const state = run([
    askHello,
    { type: "token", value: "broken half" },
    { type: "error", value: "boom" },
    { type: "ask", question: "next?" },
  ]);

  const messages = toMessages(state.turns);
  assert.equal(
    messages.some((m) => m.content === "broken half"),
    false,
  );
  assert.deepEqual(messages, [
    { role: "user", content: "hello?" },
    { role: "user", content: "next?" },
  ]);
});

test("toMessages excludes an aborted answer from history", () => {
  const state = run([
    askHello,
    { type: "token", value: "stopped early" },
    { type: "abort" },
    { type: "ask", question: "next?" },
  ]);

  assert.equal(
    toMessages(state.turns).some((m) => m.content === "stopped early"),
    false,
  );
});

test("toMessages never sends the in-flight answer back", () => {
  // The last turn's answer is still being written; sending it would duplicate.
  const state = run([askHello, { type: "token", value: "in progress" }]);

  assert.deepEqual(toMessages(state.turns), [{ role: "user", content: "hello?" }]);
});
