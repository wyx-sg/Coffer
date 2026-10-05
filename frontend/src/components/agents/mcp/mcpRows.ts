// src/components/agents/mcp/mcpRows.ts — the agent's MCP servers tab: what reaches it through Coffer, and its own direct entries.
//
// Coffer's servers are not rows: the tab names them in one "From Coffer" row.
// An own row is a direct entry in one of the agent's config files: it bypasses
// Coffer, or duplicates a registered server (`matches_resource`), or sits in a
// file that failed to parse and is then read-only. The `coffer` entry of the
// agent's config is the gateway itself, so it is never a row.
import type { KindColumn } from "@/components/agents/tabs/AgentKindTab";
import { reachesAgent } from "@/lib/agents/counts";
import { isCustomToolGroup } from "@/lib/customTools/groups";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import type { Scope } from "@/lib/hooks/useScope";

/** The fields of a registered MCP server the tab reads. */
interface McpServerLike {
  uid: string;
  name: string;
  enabled: boolean;
  scope?: Scope | null;
  config?: unknown;
}

export type OwnMcpState = "bypasses" | "duplicate" | "readOnly";

export interface OwnMcpRow {
  key: string;
  name: string;
  entry: McpEntryOut;
  state: OwnMcpState;
}

/** The command line of a stdio entry, or the URL of an http one. */
export function entryCommand(entry: Pick<McpEntryOut, "transport" | "command" | "args" | "url">) {
  return entry.transport === "stdio"
    ? [entry.command, ...entry.args].filter(Boolean).join(" ")
    : (entry.url ?? "");
}

/** The agent's own entries, in the order they were read. */
export function buildOwnMcpRows(
  entries: readonly McpEntryOut[],
  unreadableSources: ReadonlySet<string>,
): OwnMcpRow[] {
  return entries
    .filter((entry) => !entry.is_coffer)
    .map((entry) => ({
      key: `own:${entry.source}:${entry.name}`,
      name: entry.name,
      entry,
      state: unreadableSources.has(entry.source)
        ? "readOnly"
        : entry.matches_resource !== null
          ? "duplicate"
          : "bypasses",
    }));
}

function reachingNames(agentUid: string, servers: readonly McpServerLike[]): string[] {
  return servers
    .filter((server) =>
      reachesAgent(agentUid, { enabled: server.enabled, scope: server.scope ?? null }),
    )
    .map((server) => server.name);
}

/** The registered MCP servers (custom-tool groups left out) that reach this agent through the gateway. */
export function cofferMcpNames(agentUid: string, servers: readonly McpServerLike[]): string[] {
  return reachingNames(
    agentUid,
    servers.filter((s) => !isCustomToolGroup(s)),
  );
}

/** The custom-tool groups that reach this agent through the gateway. */
export function cofferToolGroupNames(
  agentUid: string,
  servers: readonly McpServerLike[],
): string[] {
  return reachingNames(agentUid, servers.filter(isCustomToolGroup));
}

/** The table's columns; the row cells follow this order. */
export function ownMcpColumns(t: (key: string) => string): KindColumn[] {
  return [
    { key: "name", header: t("agents.mcpTab.cols.name"), className: "w-[20%]" },
    { key: "command", header: t("agents.mcpTab.cols.command") },
    { key: "file", header: t("agents.mcpTab.cols.file"), className: "w-[20%]" },
    { key: "state", header: t("agents.mcpTab.cols.state"), className: "w-28" },
    { key: "actions", className: "w-40" },
  ];
}
