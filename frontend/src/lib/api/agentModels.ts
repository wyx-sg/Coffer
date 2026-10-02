// frontend/src/lib/api/agentModels.ts — request helper for
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
//
// The wire types are aliases of the agent-registry contract's schemas.
// Transport via the typed client (.agents/frontend.md §4).

import { getApiClient, unwrap } from "@/lib/api/client";
import type { components as AgentRegistryWire } from "@/lib/api/generated/agent-registry";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AgentModel = AgentRegistryWire["schemas"]["AgentModelOut"];

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const agentModelsApi = {
  /** The catalogue for one agent type. 404s on an unknown agent key. */
  list: (agentKey: string) =>
    unwrap(
      getApiClient().GET("/agent-providers/{agent_key}/models", {
        params: { path: { agent_key: agentKey } },
      }),
    ),
};
