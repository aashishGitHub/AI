// Conversation state machine.
//
// Pure and separate from the component so the ordering rules — sources arrive
// before tokens, a turn ends exactly once, an aborted turn keeps its partial
// text — can be tested without a DOM or a server.

import type { Source, StreamEvent, Usage } from "./chat";

export type Turn = {
  question: string;
  answer: string;
  sources: Source[];
  usage?: Usage;
  error?: string;
  aborted?: boolean;
};

export type State = {
  status: "idle" | "streaming";
  turns: Turn[];
};

export type Action =
  | { type: "ask"; question: string }
  | { type: "abort" }
  | { type: "retry" }
  | StreamEvent;

export const initialState: State = { status: "idle", turns: [] };

/** Replaces the final turn. Every streaming update targets it. */
function updateLast(state: State, patch: Partial<Turn>): State {
  if (state.turns.length === 0) return state;

  const turns = state.turns.slice();
  turns[turns.length - 1] = { ...turns[turns.length - 1], ...patch };
  return { ...state, turns };
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "ask":
      return {
        status: "streaming",
        turns: [...state.turns, { question: action.question, answer: "", sources: [] }],
      };

    case "retry": {
      // Drop the failed turn and re-ask it, so a transient failure doesn't
      // leave a dead entry in the transcript.
      const last = state.turns[state.turns.length - 1];
      if (!last) return state;
      return {
        status: "streaming",
        turns: [...state.turns.slice(0, -1), { question: last.question, answer: "", sources: [] }],
      };
    }

    // Citations arrive before the first token so evidence is visible while the
    // answer is still being written.
    case "sources":
      return updateLast(state, { sources: action.sources });

    case "token":
      return updateLast(state, {
        answer: (state.turns[state.turns.length - 1]?.answer ?? "") + action.value,
      });

    case "done":
      return { ...updateLast(state, { usage: action.usage }), status: "idle" };

    case "error":
      return { ...updateLast(state, { error: action.value }), status: "idle" };

    case "abort":
      // Keep whatever text already arrived: a half-answer the user stopped is
      // still worth reading, and deleting it would feel like a crash.
      return { ...updateLast(state, { aborted: true }), status: "idle" };

    default:
      return state;
  }
}

/**
 * Builds the request history from completed turns.
 *
 * Turns that errored or were aborted are excluded — replaying a partial or
 * failed answer back to the model as if it were real assistant output poisons
 * the next turn's context.
 */
export function toMessages(turns: Turn[]): { role: "user" | "assistant"; content: string }[] {
  const messages: { role: "user" | "assistant"; content: string }[] = [];

  turns.forEach((turn, i) => {
    const isLast = i === turns.length - 1;
    messages.push({ role: "user", content: turn.question });

    if (!isLast && !turn.error && !turn.aborted && turn.answer.trim() !== "") {
      messages.push({ role: "assistant", content: turn.answer });
    }
  });

  return messages;
}
