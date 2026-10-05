// frontend/src/lib/api/chat.ts — request helpers for /api/v1/chat/*
//
// One channel conversation's rename and delete (for a conversation no agent
// session exists for yet) and the interrupt of a running turn. The list is
// `agentSessionsApi.listAll`. The registry of agents a turn
// can run on lives in `agentProviders.ts`.
//
// Wire types are the chat contract's generated schemas
// (`openspec/specs/chat/contracts/api.openapi.yaml` → `generated/chat.ts`).
// Transport is the shared typed client (.agents/frontend.md §4).

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/chat";

type Schemas = components["schemas"];

/** One channel conversation: `channel_binding` names the chat it lives in. */
export type Conversation = Schemas["ConversationOut"];

/** The IM platforms a channel conversation can come from. */
export type ChannelPlatform = NonNullable<Schemas["ChannelBindingOut"]["platform"]>;

const conv = (id: string) => ({ params: { path: { id } } });

export const chatApi = {
  // Rename: the agent's own session first, then the index row (spec chat "Rename
  // and delete a conversation through its agent").
  renameConversation: (id: string, title: string): Promise<Conversation> =>
    unwrap(getApiClient().PATCH("/chat/conversations/{id}", { ...conv(id), body: { title } })),

  // Delete: permanent, in the agent as well.
  deleteConversation: (id: string): Promise<void> =>
    unwrapVoid(getApiClient().DELETE("/chat/conversations/{id}", conv(id))),

  // Stop the turn running on the conversation.
  interruptTurn: (id: string): Promise<void> =>
    unwrapVoid(getApiClient().POST("/chat/conversations/{id}/interrupt", conv(id))),
};
