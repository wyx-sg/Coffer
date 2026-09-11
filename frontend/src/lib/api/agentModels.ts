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
// Two separate answers, deliberately: the CATALOGUE is everything the installed
// agent reports, and the SELECTION is which of those the user ticked as actually
// runnable on their account. The catalogue is never narrowed by the selection —
// the curation UI renders the catalogue and ticks it, so a model that dropped
// out of the list could never be ticked back on. An empty selection means "not
// curated yet" and every model is offered; it never means "no models".

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

export interface AgentModelSelectionOut {
  /** The curated ids. Empty = not curated = the whole catalogue is offered. */
  models: string[];
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

  /** Which of the catalogue this agent offers. `[]` = not curated. */
  selection: (agentKey: string) =>
    send<AgentModelSelectionOut>(
      `/agent-providers/${encodeURIComponent(agentKey)}/models/selection`,
      "GET",
    ),

  /**
   * Replace the curated set. `[]` clears it and puts the whole catalogue back
   * on offer. 404s when no agent of this type is registered — the set lives in
   * that agent's config row.
   */
  setSelection: (agentKey: string, models: string[]) =>
    send<AgentModelSelectionOut>(
      `/agent-providers/${encodeURIComponent(agentKey)}/models/selection`,
      "PUT",
      { models },
    ),
};
