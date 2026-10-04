// src/lib/conversations/handoff.ts
// Opening the draft conversation with a prompt already typed: how a surface
// hands a chore to an agent Coffer manages (components/handoff/AgentHandoff).
// The prompt rides in the router's location STATE, never the URL — it is the
// daemon's text for this machine and must not land in history or a shared link.
// useChatController reads it once on `/conversations/new`, seeds the draft's
// agent and folder and the composer, then clears the state. Nothing is ever
// sent from here: the person reads the prompt and presses Send.
import type { NavigateFunction } from "react-router-dom";

/** The draft's route. */
export const DRAFT_PATH = "/conversations/new";

/** What a hand-off pre-fills the draft with. */
export interface ConversationHandoff {
  agentKey: string;
  /** The folder the turn runs in; null is Coffer's own workspace. */
  cwd: string | null;
  prompt: string;
}

/** Open the draft with `handoff` pre-filled. */
export function openHandoffDraft(navigate: NavigateFunction, handoff: ConversationHandoff): void {
  navigate(DRAFT_PATH, { state: { handoff } });
}

/** The hand-off in a location's state, or null when there is none or it is malformed. */
export function readHandoffState(state: unknown): ConversationHandoff | null {
  if (typeof state !== "object" || state === null || !("handoff" in state)) return null;
  const handoff: unknown = state.handoff;
  if (typeof handoff !== "object" || handoff === null) return null;
  const { agentKey, cwd, prompt } = handoff as Record<string, unknown>;
  if (typeof agentKey !== "string" || !agentKey) return null;
  if (typeof prompt !== "string" || !prompt) return null;
  if (cwd !== null && cwd !== undefined && typeof cwd !== "string") return null;
  return { agentKey, cwd: cwd || null, prompt };
}

/** The location state that opens the draft on one agent with an empty composer — an agent page's
 *  New conversation. Unlike a hand-off it carries no prompt, so the draft reads as an ordinary one. */
export function draftAgentState(agentKey: string): { draftAgent: string } {
  return { draftAgent: agentKey };
}

/** The agent a location's state opens the draft on, or null when it names none. */
export function readDraftAgentState(state: unknown): string | null {
  if (typeof state !== "object" || state === null || !("draftAgent" in state)) return null;
  const agentKey: unknown = state.draftAgent;
  return typeof agentKey === "string" && agentKey ? agentKey : null;
}
