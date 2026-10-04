// src/test/conversationFixtures.ts — conversations in the wire's full shape for
// the Conversations page's tests: a web one by default, a channel one with
// `channelBinding`, so every test builds rows the way the daemon sends them.
import type { Conversation } from "@/lib/api/chat";

type Binding = NonNullable<Conversation["channel_binding"]>;

export function makeBinding(overrides: Partial<Binding> = {}): Binding {
  return {
    channel_uid: "ch-1",
    channel: "Team bot",
    chat_id: "chat-1",
    mirror: null,
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
    archived_at: null,
    channel_binding: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    preview: null,
    running: false,
    needs_you: false,
    ...overrides,
  };
}
