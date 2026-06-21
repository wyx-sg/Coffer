// frontend/src/lib/api/chat.ts — typed fetch helpers for /api/v1/chat/*
// Hand-written wire types matching specs/008-agent-chat/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/chat/schemas.py.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ContentBlock {
  type: "text" | "tool_use" | "tool_result";
  text?: string | null;
  tool_use_id?: string | null;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
}

export type MessageRole = "user" | "assistant";
export type MessageStatus = "complete" | "streaming" | "failed";

export interface Message {
  id: string;
  conversation_id: string;
  seq: number;
  role: MessageRole;
  content: ContentBlock[];
  status: MessageStatus;
  model_id?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  created_at: string;
}

export interface MessageListOut {
  messages: Message[];
}

/** The IM channel binding behind a channel-originated conversation (ADR-021). */
export interface ChannelBinding {
  channel: string;
  chat_id: string;
}

export interface Conversation {
  id: string;
  agent_key: string;
  title: string;
  model_id: string | null;
  created_at: string;
  updated_at: string;
  /** Null for an active conversation; an ISO timestamp once archived. */
  archived_at?: string | null;
  /** The IM channel this conversation is bound to; null for a web conversation. */
  channel_binding?: ChannelBinding | null;
}

export interface ConversationListOut {
  conversations: Conversation[];
}

export interface ConversationCreate {
  /** Which agent the conversation talks to (default: the built-in agent). */
  agent_key?: string;
  /** Opaque, agent-specific configuration validated by the named agent. */
  agent_config?: Record<string, unknown> | null;
}

export interface ConversationPatch {
  title?: string | null;
  model_id?: string | null;
}

/**
 * A conversation's agent config (managed agents). `model` is the agent's own
 * per-conversation model, free-text and passed through to its CLI (ADR-024 →
 * ADR-032). `session_id` is provider-internal and not surfaced.
 */
export interface AgentConfigOut {
  cwd: string | null;
  model: string | null;
}

export interface AgentConfigPatch {
  /** Empty/whitespace or null clears the override (inherit the provider default). */
  model?: string | null;
}

export interface SendMessageRequest {
  text: string;
}

/** One agent the chat platform offers, as returned by GET /chat/agents. */
export interface AgentInfo {
  agent_key: string;
  display_name: string;
  available: boolean;
}

export interface AgentListOut {
  agents: AgentInfo[];
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function call<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) {
    return undefined as unknown as T;
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return data as T;
}

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const chatApi = {
  // Agents
  listAgents: () => call<AgentListOut>("GET", "/chat/agents"),

  // Conversations
  listConversations: (archived = false) =>
    call<ConversationListOut>("GET", `/chat/conversations?archived=${archived}`),

  createConversation: (body?: ConversationCreate) =>
    call<Conversation>("POST", "/chat/conversations", body ?? {}),

  archiveConversation: (id: string) =>
    call<Conversation>("POST", `/chat/conversations/${id}/archive`),

  unarchiveConversation: (id: string) =>
    call<Conversation>("POST", `/chat/conversations/${id}/unarchive`),

  getConversation: (id: string) => call<Conversation>("GET", `/chat/conversations/${id}`),

  updateConversation: (id: string, body: ConversationPatch) =>
    call<Conversation>("PATCH", `/chat/conversations/${id}`, body),

  // Per-conversation managed-agent model (agent_config.model), mirrors `/model`.
  getAgentConfig: (id: string) =>
    call<AgentConfigOut>("GET", `/chat/conversations/${id}/agent-config`),

  setAgentModel: (id: string, model: string | null) =>
    call<AgentConfigOut>("PATCH", `/chat/conversations/${id}/agent-config`, { model }),

  deleteConversation: (id: string) => call<void>("DELETE", `/chat/conversations/${id}`),

  // Messages
  listMessages: (conversationId: string) =>
    call<MessageListOut>("GET", `/chat/conversations/${conversationId}/messages`),

  // Enqueue a user message. Fire-and-return (202): the turn runs server-side and
  // its events arrive over the GET /events subscription, not this response.
  sendMessage: (conversationId: string, text: string) =>
    call<{ queued: boolean }>("POST", `/chat/conversations/${conversationId}/messages`, { text }),

  // Replace the pending-message queue (resume / drop / reorder).
  setPending: (conversationId: string, pending: string[]) =>
    call<{ pending: string[] }>("PUT", `/chat/conversations/${conversationId}/pending`, {
      pending,
    }),

  // Turn control
  interruptTurn: (conversationId: string) =>
    call<void>("POST", `/chat/conversations/${conversationId}/interrupt`),
};
