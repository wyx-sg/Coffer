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

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/chat";

type Schemas = components["schemas"];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** `attachment` blocks carry the file's name/mime — a channel's media or a web
 *  upload; no path (spec chat "Re-materialise attachments from persisted history"). */
export type ContentBlock = Schemas["ContentBlockOut"];

/** One file uploaded from the composer, named by the opaque id a send carries
 *  (spec chat "Upload a file for a web message"). */
export type ChatAttachment = Schemas["ChatAttachmentOut"];

export type Message = Schemas["MessageOut"];

export type MessageListOut = Schemas["MessageListOut"];

/** `archived_at` is null for an active conversation; `channel_binding` null for a web one. */
export type Conversation = Schemas["ConversationOut"];

/**
 * Where a reply typed here also goes, for a channel conversation (spec chat
 * "Show where a reply will also be sent"). Filled only by the single-conversation
 * GET; the listing leaves `channel_binding.mirror` null.
 */
export type ChannelMirror = Schemas["ChannelMirrorOut"];

/** A send's answer: `queued` behind a running turn, and what became of the
 *  reply in the conversation's channel (`mirror`, null for a web conversation). */
export type SendMessageAck = Schemas["SendMessageAck"];

/** The IM platforms a channel conversation can come from. */
export type ChannelPlatform = NonNullable<Schemas["ChannelBindingOut"]["platform"]>;

export type ConversationListOut = Schemas["ConversationListOut"];

export type ConversationBatchAction = Schemas["ConversationBatchIn"]["action"];

export type ConversationCreate = Schemas["ConversationCreate"];

export type ConversationPatch = Schemas["ConversationPatch"];

/**
 * A conversation's agent config (managed agents). `model` is the agent's own
 * per-conversation model, free-text and passed through to its CLI (the
 * coffer-model-is-an-internal-engine and model-catalogue-read-from-the-agent ADRs). `effort`
 * is the reasoning level that model is run at, which the agents that have one
 * carry beside the model rather than inside its name; null for an agent (or a
 * model) that has no such setting. `session_id` is provider-internal and not
 * surfaced.
 */
export type AgentConfigOut = Schemas["AgentConfigOut"];

/** A question the agent asked the owner: the `question` block of a reply
 *  (spec chat "Pause a turn on a question for the owner"). */
export type Question = Schemas["QuestionOut"];

/** The owner's answer to one question: option labels and/or free text. */
export type QuestionAnswerIn = Schemas["QuestionAnswerIn"];

/** The pending-message queue after a replace (spec chat "Queue messages sent during a turn"). */
export type PendingQueue = Schemas["PendingQueueOut"];

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

const conv = (id: string) => ({ params: { path: { id } } });

export const chatApi = {
  // Conversations
  // One page of the listing (spec chat "List conversations by latest
  // activity"): the caller reads as many pages as it shows, 30 and then 50, and
  // passes the abort signal of its query so a stale request is cancelled. `q`
  // is a case-insensitive substring of the title; a cursor belongs to the
  // archived flag and the `q` it was issued for.
  listConversations: (
    opts: { archived?: boolean; limit: number; cursor?: string | null; q?: string },
    signal?: AbortSignal,
  ): Promise<ConversationListOut> =>
    unwrap(
      getApiClient().GET("/chat/conversations", {
        signal,
        params: {
          query: {
            archived: opts.archived ?? false,
            limit: opts.limit,
            ...(opts.cursor ? { cursor: opts.cursor } : {}),
            ...(opts.q ? { q: opts.q } : {}),
          },
        },
      }),
    ),

  createConversation: (body: ConversationCreate) =>
    unwrap(getApiClient().POST("/chat/conversations", { body })),

  archiveConversation: (id: string) =>
    unwrap(getApiClient().POST("/chat/conversations/{id}/archive", conv(id))),

  unarchiveConversation: (id: string) =>
    unwrap(getApiClient().POST("/chat/conversations/{id}/unarchive", conv(id))),

  batchConversations: (action: ConversationBatchAction, ids: string[]) =>
    unwrap(getApiClient().POST("/chat/conversations/batch", { body: { action, ids } })),

  getConversation: (id: string) => unwrap(getApiClient().GET("/chat/conversations/{id}", conv(id))),

  updateConversation: (id: string, body: ConversationPatch) =>
    unwrap(getApiClient().PATCH("/chat/conversations/{id}", { ...conv(id), body })),

  // Per-conversation managed-agent model (agent_config.model), mirrors `/model`.
  getAgentConfig: (id: string): Promise<AgentConfigOut> =>
    unwrap(getApiClient().GET("/chat/conversations/{id}/agent-config", conv(id))),

  // Each setter sends its own field ALONE. Restating the other one would pin a
  // value the user never touched — and, worse, re-send an inherited null as an
  // explicit clear — so the two settings stay independently editable. A null or
  // blank value clears the override (inherit the provider default / let the
  // agent pick its own level).
  setAgentModel: (id: string, model: string | null): Promise<AgentConfigOut> =>
    unwrap(
      getApiClient().PATCH("/chat/conversations/{id}/agent-config", {
        ...conv(id),
        body: { model },
      }),
    ),

  setAgentEffort: (id: string, effort: string | null): Promise<AgentConfigOut> =>
    unwrap(
      getApiClient().PATCH("/chat/conversations/{id}/agent-config", {
        ...conv(id),
        body: { effort },
      }),
    ),

  deleteConversation: (id: string): Promise<void> =>
    unwrapVoid(getApiClient().DELETE("/chat/conversations/{id}", conv(id))),

  // How many conversations wait on an answer (the sidebar's Conversations badge).
  needsYouCount: (): Promise<{ count: number }> =>
    unwrap(getApiClient().GET("/chat/conversations/needs-you-count")),

  // Answer the question's next unanswered question. `index` names the one being
  // answered, so a late answer is refused (409 QUESTION_CLOSED) instead of landing
  // on the next one. Free text goes as `text` with no `selected`.
  answerQuestion: (
    conversationId: string,
    questionId: string,
    answers: QuestionAnswerIn[],
    index?: number,
  ): Promise<Question> =>
    unwrap(
      getApiClient().POST("/chat/conversations/{id}/questions/{question_id}/answer", {
        params: { path: { id: conversationId, question_id: questionId } },
        body: index === undefined ? { answers } : { answers, index },
      }),
    ),

  // Messages
  listMessages: (conversationId: string): Promise<MessageListOut> =>
    unwrap(getApiClient().GET("/chat/conversations/{id}/messages", conv(conversationId))),

  // Enqueue a user message. Fire-and-return (202): the turn runs server-side and
  // its events arrive over the GET /events subscription, not this response.
  // `attachmentIds` are uploads from `uploadAttachment`, in attach order.
  sendMessage: (
    conversationId: string,
    text: string,
    attachmentIds: string[] = [],
  ): Promise<SendMessageAck> =>
    unwrap(
      getApiClient().POST("/chat/conversations/{id}/messages", {
        ...conv(conversationId),
        body: attachmentIds.length > 0 ? { text, attachment_ids: attachmentIds } : { text },
      }),
    ),

  // Send a persisted user message again (Retry). The daemon rebuilds it from its
  // row, attachments included; a file swept since is 410 ATTACHMENT_EXPIRED.
  resendMessage: (conversationId: string, messageId: string): Promise<SendMessageAck> =>
    unwrap(
      getApiClient().POST("/chat/conversations/{id}/messages/{message_id}/resend", {
        params: { path: { id: conversationId, message_id: messageId } },
      }),
    ),

  // Upload one file for a later send. Not tied to a conversation, so a draft
  // can attach before its conversation exists. `signal` cancels it (the
  // composer does when the chip is removed).
  uploadAttachment: (file: File, signal?: AbortSignal): Promise<ChatAttachment> => {
    const form = new FormData();
    form.append("file", file, file.name);
    // A FormData body goes out with no Content-Type: the browser sets the
    // multipart boundary itself. `body` only carries the generated type.
    return unwrap(
      getApiClient().POST("/chat/attachments", {
        body: { file: "" },
        bodySerializer: () => form,
        signal,
      }),
    );
  },

  // Replace the pending-message queue (resume / drop / reorder).
  setPending: (conversationId: string, pending: string[]): Promise<PendingQueue> =>
    unwrap(
      getApiClient().PUT("/chat/conversations/{id}/pending", {
        ...conv(conversationId),
        body: { pending },
      }),
    ),

  // Turn control
  interruptTurn: (conversationId: string): Promise<void> =>
    unwrapVoid(getApiClient().POST("/chat/conversations/{id}/interrupt", conv(conversationId))),
};
