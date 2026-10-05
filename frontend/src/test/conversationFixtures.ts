// src/test/conversationFixtures.ts — sessions in the wire's full shape for the
// Conversations page's and the Sessions tab's tests, built the way the daemon
// sends them.
import type { AgentSession, AgentSessionRow } from "@/lib/api/agentSessions";

type Binding = NonNullable<AgentSession["channel_binding"]>;

export function makeBinding(overrides: Partial<Binding> = {}): Binding {
  return {
    channel_uid: "ch-1",
    channel: "Team bot",
    chat_id: "chat-1",
    platform: "seatalk",
    place: { chat_kind: "direct", thread: false, parallel_mark: null, chat_name: null },
    ...overrides,
  };
}

export function makeSession(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    session_id: "sess-1",
    title: "Test session",
    cwd: "/work/api",
    created_at: "2026-01-01T00:00:00Z",
    last_activity_at: "2026-01-01T00:00:00Z",
    conversation_id: null,
    channel_binding: null,
    running: false,
    needs_you: false,
    ...overrides,
  };
}

/** A row of the cross-agent list: a channel conversation's session by default. */
export function makeSessionRow(overrides: Partial<AgentSessionRow> = {}): AgentSessionRow {
  return {
    agent_key: "claude_code",
    session_id: "sess-1",
    conversation_id: "conv-1",
    title: "Test session",
    cwd: "/work/api",
    created_at: "2026-01-01T00:00:00Z",
    last_activity_at: "2026-01-01T00:00:00Z",
    channel_binding: makeBinding(),
    running: false,
    needs_you: false,
    ...overrides,
  };
}
