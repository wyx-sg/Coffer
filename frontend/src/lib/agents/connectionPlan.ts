// src/lib/agents/connectionPlan.ts — what a Coffer connection change writes, as change-preview items.
//
// A connection is the parts Coffer writes into an agent's own config: the
// gateway MCP entry always, the memory delivery hook while the memory feature
// is on. The daemon has no dry-run diff, so the preview is built here from what
// is known for certain — which file each part lives in, which parts are already
// installed (the connection status of a registered agent) and the command an
// installed part carries (its `detail`). A value not known yet (the uid before
// registration, the shim path before install) is written as the placeholder
// the caller passes, never invented. Pure: no React, no i18n.
import type { ChangeItem, DiffLine } from "@/components/change-preview/changeCounts";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";

export type ConnectionPartKey = "mcp" | "memory_hook";
type Part = CofferConnection["parts"][number];

export interface PlanAgent {
  row: Pick<AgentTypeOut, "type" | "config_dir" | "standard_config_dir" | "state">;
  /** The registered agent's uid; absent before registration. */
  uid?: string | null;
  /** The registered agent's connection parts; absent before registration. */
  parts?: readonly Part[];
}

export interface PlanOptions {
  /** Whether the memory feature is on (the hook part applies only then). */
  memoryOn: boolean;
  /** Words written where a value is not known yet. */
  placeholders: { uid: string; shim: string };
}

function dirname(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, "");
  const cut = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  return cut <= 0 ? trimmed : trimmed.slice(0, cut);
}

function join(dir: string, name: string): string {
  return `${dir.replace(/[\\/]+$/, "")}/${name}`;
}

/** The absolute file each part of an agent's connection is written to. */
export function connectionFiles(row: PlanAgent["row"]): Record<ConnectionPartKey, string> {
  if (row.type === "codex") {
    return {
      mcp: join(row.config_dir, "config.toml"),
      memory_hook: join(row.config_dir, "hooks.json"),
    };
  }
  // Claude Code keeps its MCP entries in ~/.claude.json beside the standard
  // directory, and in <dir>/.claude.json when pointed at another one.
  const mcpDir =
    row.config_dir === row.standard_config_dir ? dirname(row.config_dir) : row.config_dir;
  return { mcp: join(mcpDir, ".claude.json"), memory_hook: join(row.config_dir, "settings.json") };
}

/** The parts a connect would install: every applicable part not yet installed. */
export function partsToInstall(agent: PlanAgent, memoryOn: boolean): ConnectionPartKey[] {
  if (agent.parts) {
    return agent.parts.filter((p) => !p.installed).map((p) => p.key as ConnectionPartKey);
  }
  return memoryOn ? ["mcp", "memory_hook"] : ["mcp"];
}

/** The parts a disconnect would remove: every installed part. */
function partsToRemove(agent: PlanAgent): ConnectionPartKey[] {
  return (agent.parts ?? []).filter((p) => p.installed).map((p) => p.key as ConnectionPartKey);
}

/** Whether adding the agent creates its config directory (installed, never run, not added). */
export function createsConfigDir(agent: PlanAgent): boolean {
  return !agent.uid && agent.row.state === "installed_never_run";
}

function detailOf(agent: PlanAgent, key: ConnectionPartKey): string | null {
  return agent.parts?.find((p) => p.key === key)?.detail ?? null;
}

function entryLines(agent: PlanAgent, opts: PlanOptions): { hunk: string; lines: string[] } {
  const shim = detailOf(agent, "mcp") ?? opts.placeholders.shim;
  const uid = agent.uid || opts.placeholders.uid;
  if (agent.row.type === "codex") {
    return {
      hunk: "mcp_servers.coffer",
      lines: ["[mcp_servers.coffer]", `command = "${shim}"`, `args = ["--agent-uid", "${uid}"]`],
    };
  }
  return {
    hunk: "mcpServers",
    lines: [`"coffer": {`, `  "command": "${shim}",`, `  "args": ["--agent-uid", "${uid}"]`, `},`],
  };
}

function hookLines(agent: PlanAgent, opts: PlanOptions): { hunk: string; lines: string[] } {
  const uid = agent.uid || opts.placeholders.uid;
  const command = detailOf(agent, "memory_hook") ?? `coffer memory context --agent-uid ${uid} …`;
  return {
    hunk: "hooks.SessionStart",
    lines: [`{ "hooks": [{ "type": "command",`, `    "command": "${command}" }] },`],
  };
}

function partItem(
  agent: PlanAgent,
  key: ConnectionPartKey,
  kind: "add" | "remove",
  opts: PlanOptions,
): ChangeItem {
  const { hunk, lines } = key === "mcp" ? entryLines(agent, opts) : hookLines(agent, opts);
  const diff: DiffLine[] = [{ kind: "hunk", text: hunk }, ...lines.map((text) => ({ kind, text }))];
  return {
    id: `${agent.row.type}:${key}`,
    agentType: agent.row.type,
    path: abbreviateHomePath(connectionFiles(agent.row)[key]),
    op: "modify",
    added: kind === "add" ? lines.length : undefined,
    removed: kind === "remove" ? lines.length : undefined,
    diff,
  };
}

/** Items for Add / Connect / Repair: the directory a never-run agent gets, then each missing part. */
export function planConnect(agents: readonly PlanAgent[], opts: PlanOptions): ChangeItem[] {
  return agents.flatMap((agent) => {
    const items: ChangeItem[] = [];
    if (createsConfigDir(agent)) {
      items.push({
        id: `${agent.row.type}:dir`,
        agentType: agent.row.type,
        path: `${abbreviateHomePath(agent.row.config_dir)}/`,
        op: "add",
      });
    }
    for (const key of partsToInstall(agent, opts.memoryOn)) {
      items.push(partItem(agent, key, "add", opts));
    }
    return items;
  });
}

/** Items for Disconnect: each installed part, with Coffer's lines removed. */
export function planDisconnect(agents: readonly PlanAgent[], opts: PlanOptions): ChangeItem[] {
  return agents.flatMap((agent) =>
    partsToRemove(agent).map((key) => partItem(agent, key, "remove", opts)),
  );
}
