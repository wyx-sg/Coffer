// src/lib/sessions/rows.ts — the one row shape the Conversations list and an
// agent's Sessions tab share (components/sessions/SessionRow). A conversation
// and an agent's native session say the same things about themselves, under
// different field names; these two functions are the whole of that difference.
import type { Conversation } from "@/lib/api/chat";
import type { AgentSession } from "@/lib/api/agentSessions";

/** @ui-only The chat a row came from: both wire shapes carry it, identical. */
export type SessionChannel = NonNullable<Conversation["channel_binding"]>;

/** @ui-only A list row, whichever list it is in. */
export interface SessionRowData {
  /** The conversation id, or the native session id. */
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

export function conversationRow(c: Conversation): SessionRowData {
  return {
    id: c.id,
    sessionId: c.session_id,
    conversationId: c.id,
    title: c.title,
    cwd: c.cwd,
    activityAt: c.updated_at,
    running: c.running,
    needsYou: c.needs_you,
    channel: c.channel_binding,
    agentKey: c.agent_key,
  };
}

export function sessionRow(s: AgentSession): SessionRowData {
  return {
    id: s.session_id,
    sessionId: s.session_id,
    conversationId: s.conversation_id,
    title: s.title,
    cwd: s.cwd,
    activityAt: s.last_activity_at ?? s.created_at,
    running: s.running,
    needsYou: s.needs_you,
    channel: s.channel_binding,
    agentKey: null,
  };
}
