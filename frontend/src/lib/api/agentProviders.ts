// frontend/src/lib/api/agentProviders.ts — typed fetch helper for
// /api/v1/agent-providers.
//
// The agents the turn platform can run a turn on, with an availability flag
// per agent (its CLI is on PATH, or it is not). The channel editor uses this
// to offer the agents a channel may be bound to. It carried a `/chat` prefix
// while a web chat page existed; the registry outlived the page.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

/** One agent the turn platform offers. */
export interface AgentProviderInfo {
  agent_key: string;
  display_name: string;
  available: boolean;
}

export interface AgentProviderListOut {
  agents: AgentProviderInfo[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
  });
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

export const agentProvidersApi = {
  list: () => get<AgentProviderListOut>("/agent-providers"),
};
