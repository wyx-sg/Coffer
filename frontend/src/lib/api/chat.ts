// frontend/src/lib/api/chat.ts — request helpers for /api/v1/chat/*
//
// Conversations, messages, the pending queue and interrupt — the surface the
// web Chat page talks to. The registry of agents a turn can run on is NOT here:
// it outlived the page under an honest name and lives in `agentProviders.ts`.
//
// Wire types are the chat contract's generated schemas
// (`openspec/specs/chat/contracts/api.openapi.yaml` → `generated/chat.ts`), re-exported
// under the names the hooks and pages already import. Transport is the shared
// `call` (.agents/frontend.md §4).

import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/chat";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** `attachment` blocks carry the file's name/mime (channel media); no path (FR-034). */
export type ContentBlock = Schemas["ContentBlockOut"];

export type Message = Schemas["MessageOut"];

export type MessageListOut = Schemas["MessageListOut"];

/**
 * The IM channel binding behind a channel-originated conversation (ADR
 * chat-single-owner-live-mirror).
 */

/** `archived_at` is null for an active conversation; `channel_binding` null for a web one. */
export type Conversation = Schemas["ConversationOut"];

export type ConversationListOut = Schemas["ConversationListOut"];

export type ConversationCreate = Schemas["ConversationCreate"];

export type ConversationPatch = Schemas["ConversationPatch"];

/**
 * A conversation's agent config (managed agents). `model` is the agent's own
 * per-conversation model, free-text and passed through to its CLI (the
 * builtin-agent-is-internal-capability and provider-switching ADRs). `effort`
 * is the reasoning level that model is run at, which the agents that have one
 * carry beside the model rather than inside its name; null for an agent (or a
 * model) that has no such setting. `session_id` is provider-internal and not
 * surfaced.
 */
export type AgentConfigOut = Schemas["AgentConfigOut"];

/**
 * A patch that names one field leaves the other alone; see `setAgentModel`.
 * Empty/whitespace or null clears the override (inherit the provider default /
 * let the agent pick its own level).
 */

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const chatApi = {
  // Conversations
  listConversations: (archived = false) =>
    call<ConversationListOut>(`/chat/conversations?archived=${archived}`),

  createConversation: (body?: ConversationCreate) =>
    call<Conversation>("/chat/conversations", { method: "POST", body: body ?? {} }),

  archiveConversation: (id: string) =>
    call<Conversation>(`/chat/conversations/${id}/archive`, { method: "POST" }),

  unarchiveConversation: (id: string) =>
    call<Conversation>(`/chat/conversations/${id}/unarchive`, { method: "POST" }),

  getConversation: (id: string) => call<Conversation>(`/chat/conversations/${id}`),

  updateConversation: (id: string, body: ConversationPatch) =>
    call<Conversation>(`/chat/conversations/${id}`, { method: "PATCH", body }),

  // Per-conversation managed-agent model (agent_config.model), mirrors `/model`.
  getAgentConfig: (id: string) => call<AgentConfigOut>(`/chat/conversations/${id}/agent-config`),

  // Each setter sends its own field ALONE. Restating the other one would pin a
  // value the user never touched — and, worse, re-send an inherited null as an
  // explicit clear — so the two settings stay independently editable.
  setAgentModel: (id: string, model: string | null) =>
    call<AgentConfigOut>(`/chat/conversations/${id}/agent-config`, {
      method: "PATCH",
      body: { model },
    }),

  setAgentEffort: (id: string, effort: string | null) =>
    call<AgentConfigOut>(`/chat/conversations/${id}/agent-config`, {
      method: "PATCH",
      body: { effort },
    }),

  deleteConversation: (id: string) => call<void>(`/chat/conversations/${id}`, { method: "DELETE" }),

  // Messages
  listMessages: (conversationId: string) =>
    call<MessageListOut>(`/chat/conversations/${conversationId}/messages`),

  // Enqueue a user message. Fire-and-return (202): the turn runs server-side and
  // its events arrive over the GET /events subscription, not this response.
  sendMessage: (conversationId: string, text: string) =>
    call<{ queued: boolean }>(`/chat/conversations/${conversationId}/messages`, {
      method: "POST",
      body: { text },
    }),

  // Replace the pending-message queue (resume / drop / reorder).
  setPending: (conversationId: string, pending: string[]) =>
    call<{ pending: string[] }>(`/chat/conversations/${conversationId}/pending`, {
      method: "PUT",
      body: { pending },
    }),

  // Turn control
  interruptTurn: (conversationId: string) =>
    call<void>(`/chat/conversations/${conversationId}/interrupt`, { method: "POST" }),
};
