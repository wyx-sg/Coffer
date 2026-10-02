// src/components/agents/overview/connectionCopy.ts — what the Connection card says for each state.
//
// Pure: the card's title/body keys and its part rows are derived from the
// agent's row state, the connection's parts and Coffer's hook health, so the
// sentence always names the part that is actually off.
import type { StatusTone } from "@/lib/statusTone";
import type { AgentRowState } from "@/lib/agents/rowState";
import type { CofferConnection, CofferHook } from "@/lib/api/agents";

/** The states the Connection card renders (problem states replace the whole tab). */
export type ConnectionCardState = Extract<
  AgentRowState,
  "connected" | "not_connected" | "needs_repair" | "disabled"
>;

export function isConnectionCardState(state: AgentRowState): state is ConnectionCardState {
  return (
    state === "connected" ||
    state === "not_connected" ||
    state === "needs_repair" ||
    state === "disabled"
  );
}

const K = "agents.overviewTab.connection";

/** The i18n key of the card's sentence. */
export function connectionBodyKey(
  state: ConnectionCardState,
  parts: CofferConnection["parts"],
  hook: CofferHook | null | undefined,
): string {
  const hasHook = parts.some((p) => p.key === "memory_hook");
  if (state === "disabled") return `${K}.body.disabled`;
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
  return state === "connected" && hook?.health === "current" && hook.trust === "untrusted";
}

/** Only the memory hook is off (the `coffer` MCP entry is in place): Repair fixes just the hook. */
export function repairsOnlyHook(parts: CofferConnection["parts"] | undefined): boolean {
  if (!parts) return false;
  const mcp = parts.find((p) => p.key === "mcp");
  const hook = parts.find((p) => p.key === "memory_hook");
  return (!mcp || mcp.installed) && !!hook && !hook.installed;
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

type PartHealth = "current" | "stale" | "missing" | "idle" | "untrusted";

const HEALTH_TONE: Record<PartHealth, StatusTone> = {
  current: "ok",
  stale: "warn",
  missing: "warn",
  idle: "off",
  untrusted: "warn",
};

export function partHealthTone(health: PartHealth): StatusTone {
  return HEALTH_TONE[health];
}

/** A part's health word: Idle while disabled, else installed-and-current / out of date / missing. */
export function partHealth(
  part: CofferConnection["parts"][number],
  hook: CofferHook | null | undefined,
  disabled: boolean,
): PartHealth {
  if (disabled) return "idle";
  if (!part.installed) return "missing";
  if (part.key === "memory_hook" && hook) {
    return hook.health === "current" && hook.trust === "untrusted" ? "untrusted" : hook.health;
  }
  return "current";
}
