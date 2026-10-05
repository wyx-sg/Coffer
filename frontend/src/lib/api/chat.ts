// frontend/src/lib/api/chat.ts — request helpers for /api/v1/chat/*
//
// The channel conversations the Conversations page lists, their rename and
// delete, and the interrupt of a running turn. The registry of agents a turn
// can run on lives in `agentProviders.ts`.
//
// Wire types are the chat contract's generated schemas
// (`openspec/specs/chat/contracts/api.openapi.yaml` → `generated/chat.ts`).
// Transport is the shared typed client (.agents/frontend.md §4).

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/chat";

type Schemas = components["schemas"];

/** One channel conversation as the list shows it: `channel_binding` names the chat it lives in. */
export type Conversation = Schemas["ConversationOut"];

/** The IM platforms a channel conversation can come from. */
export type ChannelPlatform = NonNullable<Schemas["ChannelBindingOut"]["platform"]>;

export type ConversationListOut = Schemas["ConversationListOut"];

const conv = (id: string) => ({ params: { path: { id } } });

export const chatApi = {
  // One page of the listing (spec chat "List conversations by latest
  // activity"): the caller reads as many pages as it shows, 30 and then 50, and
  // passes the abort signal of its query so a stale request is cancelled. `q`
  // is a case-insensitive substring of the title or working directory; `source`
  // (channel uids) and `agent` narrow the list; a cursor belongs to the filters it was issued for.
  listConversations: (
    opts: {
      limit: number;
      cursor?: string | null;
      q?: string;
      /** Channel uids and agent keys; empty is every one. */
      source?: readonly string[];
      agent?: readonly string[];
    },
    signal?: AbortSignal,
  ): Promise<ConversationListOut> =>
    unwrap(
      getApiClient().GET("/chat/conversations", {
        signal,
        params: {
          query: {
            limit: opts.limit,
            ...(opts.cursor ? { cursor: opts.cursor } : {}),
            ...(opts.q ? { q: opts.q } : {}),
            ...(opts.source?.length ? { source: opts.source.join(",") } : {}),
            ...(opts.agent?.length ? { agent: opts.agent.join(",") } : {}),
          },
        },
      }),
    ),

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
