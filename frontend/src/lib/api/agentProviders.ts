// frontend/src/lib/api/agentProviders.ts — request helper for
// /api/v1/agent-providers.
//
// The agents the turn platform can run a turn on, with an availability flag
// per agent (its CLI is on PATH, or it is not). The channel editor uses this
// to offer the agents a channel may be bound to. It carried a `/chat` prefix
// while a web chat page existed; the registry outlived the page.
//
// Wire types from the chat contract (where the route lives); transport via
// the shared `call` (.agents/frontend.md §4).

import { call } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/chat";

/** One agent the turn platform offers. */
export type AgentProviderInfo = components["schemas"]["AgentProviderOut"];

export type AgentProviderListOut = components["schemas"]["AgentProviderListOut"];

export const agentProvidersApi = {
  list: () => call<AgentProviderListOut>("/agent-providers"),
};
