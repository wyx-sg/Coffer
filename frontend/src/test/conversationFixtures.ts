// src/test/conversationFixtures.ts — conversations in the wire's full shape for
// the Conversations page's tests: a channel conversation by default (the list
// holds nothing else), built the way the daemon sends them.
import type { AgentSession } from "@/lib/api/agentSessions";
import type { Conversation } from "@/lib/api/chat";

type Binding = NonNullable<Conversation["channel_binding"]>;

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

export function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "conv-1",
    agent_key: "claude_code",
    title: "Test Conv",
    channel_binding: makeBinding(),
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    cwd: "/work/api",
    session_id: "sess-1",
    running: false,
    needs_you: false,
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
