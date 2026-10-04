// src/lib/agents/rowState.ts — the one state an agent reads as, on the list row, the detail header and Overview.
//
// Two signals meet here: detection (is the program installed, does its config
// directory exist — `AgentTypeOut.state`) and, for an added agent, Coffer's own
// view of it (how much of its Coffer connection is in place).
// Detection wins: an added agent whose program is gone reads as config left
// behind (its directory is still there) or not found (nothing is), because
// nothing Coffer writes can reach it until it is back.
import type { StatusTone } from "@/lib/statusTone";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";

export type AgentRowState =
  /** Neither program nor directory, not added. */
  | "not_installed"
  /** A directory with no program behind it. */
  | "config_left_behind"
  /** Added, but neither its program nor its directory is here any more. */
  | "not_found"
  /** Program installed, never run (no directory yet), not added. */
  | "never_run"
  /** Program and directory found, not added. */
  | "not_added"
  | "connected"
  /** Some of the connection's parts are in place (`partial`). */
  | "needs_repair"
  | "not_connected"
  /** Added, connection not read yet. */
  | "checking";

export function agentRowState(
  row: Pick<AgentTypeOut, "state" | "uid">,
  connection?: CofferConnection["state"],
): AgentRowState {
  const added = !!row.uid;
  if (row.state === "config_only") return "config_left_behind";
  if (row.state === "missing") return added ? "not_found" : "not_installed";
  if (!added) return row.state === "installed_never_run" ? "never_run" : "not_added";
  if (connection === undefined) return "checking";
  if (connection === "connected") return "connected";
  return connection === "partial" ? "needs_repair" : "not_connected";
}

const TONE: Record<AgentRowState, StatusTone> = {
  not_installed: "off",
  config_left_behind: "warn",
  not_found: "err",
  never_run: "off",
  not_added: "off",
  connected: "ok",
  needs_repair: "warn",
  // One off state, gray: a newly found agent and a disconnected one both read
  // Not connected, and neither is broken.
  not_connected: "off",
  checking: "off",
};

export function agentRowTone(state: AgentRowState): StatusTone {
  return TONE[state];
}

/**
 * The i18n key of the state's word (`agents.state.<state>`). A newly found
 * agent (never run, not added) and a disconnected one are the same off state,
 * so they read the same word.
 */
export function agentRowStateKey(state: AgentRowState): string {
  const word = state === "not_added" || state === "never_run" ? "not_connected" : state;
  return `agents.state.${word}`;
}

/** Whether the state can be added from its row (the daemon's `addable` also has to agree). */
export function isAddableState(state: AgentRowState): boolean {
  return state === "not_added" || state === "never_run";
}
