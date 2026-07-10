// lib/api/agentCapabilities.ts — the FR-003a capability-matrix slice the UI
// consumes. A false flag renders a uniform "not supported" state instead of an
// empty table or a raw error (ADR-042 presentation amendment 2026-07-10).
import type { AgentOut } from "@/lib/api/agents";

export interface AgentCapabilities {
  plugins: boolean;
  transcripts: boolean;
  connections: boolean;
}

/** Facet support with a safe default: an agent payload without the matrix
 * (older fixture, mid-rollout daemon) is treated as fully capable. */
export function facetSupported(agent: AgentOut, facet: keyof AgentCapabilities): boolean {
  return agent.capabilities?.[facet] ?? true;
}
