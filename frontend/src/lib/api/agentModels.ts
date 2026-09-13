// frontend/src/lib/api/agentModels.ts — typed fetch helper for
// /api/v1/agent-providers/{agent_key}/models.
//
// The agent's model catalogue. It replaces the hardcoded per-agent constant the
// frontend used to carry: the backend is the single source of truth, and it in
// turn writes down no model of its own — every entry is read back from the
// installed agent. So a newly released model reaches the UI with no release of
// anything. What an entry IS differs by agent, because each agent's own picker
// differs: Codex names concrete, version-bearing models, while Claude Code
// names exactly the tier aliases its CLI accepts (`opus`, `sonnet`, …), each
// labelled with the model that alias resolves to today ("Opus 5"). An alias is
// not the vaguer answer it looks like — it is the only one that stays true
// across an account's entitlements, and that knowledge lives on the CLI's
// server, not here. The order the backend returns is the agent's own and must
// be preserved.
//
// One question, one answer: "what can this agent be put on". Nothing narrows
// it, so there is no per-agent selection endpoint to call here. An entry also
// carries its reasoning-effort levels beside its id, because an effort is a
// setting ON a model rather than part of its name, and only the agent knows
// which of its models take one.

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
  /**
   * The reasoning-effort levels this model can be run at, in the order the
   * agent named them; empty when it takes no such setting. Codex's entries
   * carry levels, Claude Code's carry none.
   */
  efforts: string[];
  /** The level the agent would pick itself, or null when it named none. */
  default_effort: string | null;
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
