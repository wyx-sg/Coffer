// src/lib/sessions/rows.ts — the one row shape the Conversations list and an
// agent's Sessions tab share (components/sessions/SessionRow). Both lists are
// agent sessions; the cross-agent rows additionally say whose they are.
import type { AgentSession, AgentSessionRow } from "@/lib/api/agentSessions";

/** @ui-only The chat a row came from. */
export type SessionChannel = NonNullable<AgentSession["channel_binding"]>;

/** @ui-only A list row, whichever list it is in. */
export interface SessionRowData {
  /** The native session id; the conversation id for a channel conversation no turn has run on. */
  id: string;
  /** The agent's native session id: what opens in a terminal. Null until a turn has run. */
  sessionId: string | null;
  /** The conversation this row is, or points at: what Stop interrupts. */
  conversationId: string | null;
  title: string;
  /** The working directory, when the agent reports one. */
  cwd: string | null;
  /** ISO timestamp of the last activity; null when the agent did not say. */
  activityAt: string | null;
  running: boolean;
  needsYou: boolean;
  channel: SessionChannel | null;
  /** The agent's registry key; set where the list spans agents (Conversations). */
  agentKey: string | null;
}

export function sessionRow(s: AgentSession | AgentSessionRow): SessionRowData {
  return {
    id: s.session_id ?? s.conversation_id ?? "",
    sessionId: s.session_id,
    conversationId: s.conversation_id,
    title: s.title,
    cwd: s.cwd,
    activityAt: s.last_activity_at ?? s.created_at,
    running: s.running,
    needsYou: s.needs_you,
    channel: s.channel_binding,
    agentKey: "agent_key" in s ? s.agent_key : null,
  };
}
