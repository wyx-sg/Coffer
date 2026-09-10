// frontend/src/lib/api/agentModels.ts — typed fetch helper for
// /api/v1/agent-providers/{agent_key}/models.
//
// The agent's model catalogue. It replaces the hardcoded per-agent constant the
// frontend used to carry: the backend is the single source of truth, and it in
// turn writes down no model of its own — every entry is read back from the
// installed agent. So a newly released model reaches the UI with no release of
// anything. The list mixes the CLI's own tier aliases with the concrete,
// version-bearing models it reported, tagged by `source` so the UI can say
// where each came from; the order the backend returns is meaningful (aliases
// first) and must be preserved.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Where an id came from: `"alias"` = a tier alias the CLI accepts, which
 * always resolves to the newest model in that tier and so names no version;
 * `"discovered"` = a concrete, version-bearing model the agent reported. Kept a
 * plain string — the backend may add sources the frontend has no branch for. */
export type AgentModelSource = string;

export interface AgentModel {
  /** The id passed VERBATIM to the agent's CLI — never a display name. */
  id: string;
  label: string;
  description: string;
  source: AgentModelSource;
}

export interface AgentModelsOut {
  models: AgentModel[];
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(err?.code ?? "INTERNAL_ERROR", err?.message ?? `request failed: ${r.status}`);
  }
  return data as T;
}

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const agentModelsApi = {
  /** The catalogue for one agent type. 404s on an unknown agent key. */
  list: (agentKey: string) =>
    get<AgentModelsOut>(`/agent-providers/${encodeURIComponent(agentKey)}/models`),
};
