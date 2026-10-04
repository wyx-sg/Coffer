// src/components/agents/overview/connectionCopy.ts — what the Connection card says for each state.
//
// Pure: the card's title/body keys and its part rows are derived from the
// agent's row state, the connection's parts and Coffer's hook health, so the
// sentence always names the part that is actually off.
import type { StatusTone } from "@/lib/statusTone";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { CofferConnection, CofferHook } from "@/lib/api/agents";
import { hookNotApproved } from "@/lib/agents/hookRows";

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
export function connectionBodyKey(
  state: ConnectionCardState,
  parts: CofferConnection["parts"],
  hook: CofferHook | null | undefined,
): string {
  const hasHook = parts.some((p) => p.key === "memory_hook");
  if (hookAwaitsApproval(state, hook)) return `${K}.body.hookUntrusted`;
  if (state === "connected") return `${K}.body.${hasHook ? "connected" : "connectedMcpOnly"}`;
  if (state === "not_connected")
    return `${K}.body.${hasHook ? "notConnected" : "notConnectedMcpOnly"}`;
  const mcp = parts.find((p) => p.key === "mcp");
  if (mcp && !mcp.installed) return `${K}.body.mcpMissing`;
  return `${K}.body.${hook?.health === "stale" ? "hookStale" : "hookMissing"}`;
}

/**
 * Everything Coffer wrote is in place and current, but the agent will not run
 * Coffer's hook until the user approves it (Codex's `/hooks`). Coffer never
 * approves it for the user, so the card says how and offers the command.
 */
export function hookAwaitsApproval(
  state: AgentRowState,
  hook: CofferHook | null | undefined,
): boolean {
  return state === "connected" && hookNotApproved(hook);
}

/** The events Coffer's hook sits on — the listing names them comma-joined. */
export function hookEventCount(hook: CofferHook): number {
  return new Set(
    hook.event
      .split(",")
      .map((e) => e.trim())
      .filter(Boolean),
  ).size;
}

type PartHealth = "current" | "stale" | "missing" | "notSet" | "untrusted";

const HEALTH_TONE: Record<PartHealth, StatusTone> = {
  current: "ok",
  stale: "warn",
  missing: "warn",
  notSet: "off",
  untrusted: "warn",
};

export function partHealthTone(health: PartHealth): StatusTone {
  return HEALTH_TONE[health];
}

/** A part's health word: Not set before it was ever connected,
 *  else installed-and-current / out of date / missing. */
export function partHealth(
  part: CofferConnection["parts"][number],
  hook: CofferHook | null | undefined,
  state: ConnectionCardState,
): PartHealth {
  if (!part.installed) return state === "not_connected" ? "notSet" : "missing";
  if (part.key === "memory_hook" && hook) {
    return hookNotApproved(hook) ? "untrusted" : hook.health;
  }
  return "current";
}
