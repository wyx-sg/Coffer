// frontend/src/lib/api/agentProviders.ts — request helper for
// /api/v1/agent-providers.
//
// The agents the turn platform can run a turn on, with an availability flag
// per agent (its CLI is on PATH, or it is not). The channel editor uses this
// to offer the agents a channel may be bound to. It carried a `/chat` prefix
// while a web chat page existed; the registry outlived the page.
//
// Wire types from the chat contract (where the route lives); transport via
// the typed client (.agents/frontend.md §4).

import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/chat";

/** One agent the turn platform offers. */
export type AgentProviderInfo = components["schemas"]["AgentProviderOut"];

export const agentProvidersApi = {
  list: () => unwrap(getApiClient().GET("/agent-providers")),
};
