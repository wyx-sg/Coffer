// frontend/src/test/chatEvents.ts
//
// Build the chat event stream's `AgentEvent`s for tests. The wire carries a
// `type` discriminator in every payload that equals the SSE event name, and the
// contract makes a few nullable fields required; `ev` supplies both so a
// fixture names only what it cares about.

import type { AgentEvent } from "@/lib/chat/streamClient";

type Data<E extends AgentEvent["event"]> = Extract<AgentEvent, { event: E }>["data"];

const DEFAULTS: { [E in AgentEvent["event"]]?: Partial<Data<E>> } = {
  turn_done: { prompt_tokens: null, completion_tokens: null },
  tool_result: { output: null, error: null },
};

export function ev<E extends AgentEvent["event"]>(
  event: E,
  data: Partial<Omit<Data<E>, "type">> = {},
): AgentEvent {
  return { event, data: { ...DEFAULTS[event], ...data, type: event } } as AgentEvent;
}
