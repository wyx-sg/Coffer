// src/components/agents/overview/connectionCopy.ts — what the Connection card says for each state.
//
// Pure: the card's title/body keys and its part rows are derived from the
// agent's row state and the connection's parts, so the sentence always names
// the part that is actually off.
import type { StatusTone } from "@/lib/statusTone";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { CofferConnection } from "@/lib/api/agents";

/** The states the Connection card renders (problem states replace the whole tab). */
export type ConnectionCardState = Extract<
  AgentRowState,
  "connected" | "not_connected" | "needs_repair"
>;

export function isConnectionCardState(state: AgentRowState): state is ConnectionCardState {
  return state === "connected" || state === "not_connected" || state === "needs_repair";
}

const K = "agents.overviewTab.connection";

/** The i18n key of the card's sentence. */
export function connectionBodyKey(state: ConnectionCardState): string {
  if (state === "connected") return `${K}.body.connected`;
  if (state === "not_connected") return `${K}.body.notConnected`;
  return `${K}.body.mcpMissing`;
}

type PartHealth = "current" | "missing" | "notSet";

const HEALTH_TONE: Record<PartHealth, StatusTone> = {
  current: "ok",
  missing: "warn",
  notSet: "off",
};

export function partHealthTone(health: PartHealth): StatusTone {
  return HEALTH_TONE[health];
}

/** A part's health word: Not set before it was ever connected, else in place or missing. */
export function partHealth(
  part: CofferConnection["parts"][number],
  state: ConnectionCardState,
): PartHealth {
  if (!part.installed) return state === "not_connected" ? "notSet" : "missing";
  return "current";
}
