// src/lib/conversations/handoff.ts
// Opening the draft conversation with a prompt already typed: how a surface
// hands a chore to an agent Coffer manages (components/handoff/AgentHandoff).
// The prompt rides in the router's location STATE, never the URL — it is the
// daemon's text for this machine and must not land in history or a shared link.
// useChatController reads it once on `/conversations/new`, seeds the draft's
// agent and folder and the composer, then clears the state. A hand-off is
// sent only by the person pressing Send, except one marked `autoSend` (Tidy):
// the controller sends its prompt once the draft is seeded.
import type { NavigateFunction } from "react-router-dom";

/** The draft's route. */
export const DRAFT_PATH = "/conversations/new";

/** What a hand-off pre-fills the draft with. */
export interface ConversationHandoff {
  agentKey: string;
  /** The folder the turn runs in; null is Coffer's own workspace. */
  cwd: string | null;
  prompt: string;
  /** Send the prompt at once instead of leaving it in the composer. */
  autoSend?: boolean;
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
  const { agentKey, cwd, prompt, autoSend } = handoff as Record<string, unknown>;
  if (typeof agentKey !== "string" || !agentKey) return null;
  if (typeof prompt !== "string" || !prompt) return null;
  if (cwd !== null && cwd !== undefined && typeof cwd !== "string") return null;
  return { agentKey, cwd: cwd || null, prompt, ...(autoSend === true ? { autoSend } : {}) };
}
