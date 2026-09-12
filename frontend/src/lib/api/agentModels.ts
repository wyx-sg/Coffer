// frontend/src/lib/api/agentModels.ts — typed fetch helper for
// /api/v1/agent-providers/{agent_key}/models.
//
// The agent's model catalogue. It replaces the hardcoded per-agent constant the
// frontend used to carry: the backend is the single source of truth, and it in
// turn writes down no model of its own — every entry is read back from the
// installed agent. So a newly released model reaches the UI with no release of
// anything. Concrete, version-bearing models only — the CLIs' tier aliases
// (`sonnet`, `opus`, `best`, `sonnet[1m]`, …) are not listed, since each
// resolves to a model already in the list. The order the backend returns is
// meaningful (newest first) and must be preserved.
//
// One question, one answer: "what can this agent be put on". Nothing narrows
// it. Curation belongs to a surface with an AUDIENCE — a channel's allowed
// range (spec channels FR-071) — not to the agent, so there is no per-agent
// selection endpoint to call here.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentModel {
  /** The id passed VERBATIM to the agent's CLI — never a display name. */
  id: string;
  label: string;
  description: string;
}

export interface AgentModelsOut {
  models: AgentModel[];
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
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

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const agentModelsApi = {
  /** The catalogue for one agent type. 404s on an unknown agent key. */
  list: (agentKey: string) =>
    send<AgentModelsOut>(`/agent-providers/${encodeURIComponent(agentKey)}/models`, "GET"),
};
