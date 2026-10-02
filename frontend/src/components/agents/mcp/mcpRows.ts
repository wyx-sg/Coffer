// src/components/agents/mcp/mcpRows.ts — the agent's MCP servers tab rows: Coffer's gateway servers and its own direct entries.
//
// One table lists both (spec agent-registry "Filter an agent's installed kinds
// by owner"). A Coffer row is a registered MCP server that reaches this agent,
// served through the `coffer` entry of the agent's config — that entry is the
// gateway itself, so it is never a row. An own row is a direct entry in one of
// the agent's config files: it bypasses Coffer, or duplicates a registered
// server (`matches_resource`), or sits in a file that failed to parse and is
// then read-only.
import { reachesAgent } from "@/lib/agents/counts";
import type { McpEntryOut } from "@/lib/api/agents-workspace";
import type { Scope } from "@/lib/hooks/useScope";

/** The fields of a registered MCP server the tab reads. */
interface McpServerLike {
  uid: string;
  name: string;
  enabled: boolean;
  scope?: Scope | null;
}

interface CofferMcpRow {
  key: string;
  owner: "coffer";
  name: string;
}

export type OwnMcpState = "bypasses" | "duplicate" | "readOnly";

export interface OwnMcpRow {
  key: string;
  owner: "own";
  name: string;
  entry: McpEntryOut;
  state: OwnMcpState;
}

export type McpRow = CofferMcpRow | OwnMcpRow;

/** The command line of a stdio entry, or the URL of an http one. */
export function entryCommand(entry: Pick<McpEntryOut, "transport" | "command" | "args" | "url">) {
  return entry.transport === "stdio"
    ? [entry.command, ...entry.args].filter(Boolean).join(" ")
    : (entry.url ?? "");
}

/** Own entries first (they are what the user acts on), then Coffer's. */
export function buildMcpRows(
  agentUid: string,
  servers: readonly McpServerLike[],
  entries: readonly McpEntryOut[],
  unreadableSources: ReadonlySet<string>,
): McpRow[] {
  const own = entries
    .filter((entry) => !entry.is_coffer)
    .map(
      (entry): OwnMcpRow => ({
        key: `own:${entry.source}:${entry.name}`,
        owner: "own",
        name: entry.name,
        entry,
        state: unreadableSources.has(entry.source)
          ? "readOnly"
          : entry.matches_resource !== null
            ? "duplicate"
            : "bypasses",
      }),
    );
  const coffer = servers
    .filter((server) =>
      reachesAgent(agentUid, { enabled: server.enabled, scope: server.scope ?? null }),
    )
    .map(
      (server): CofferMcpRow => ({
        key: `coffer:${server.uid}`,
        owner: "coffer",
        name: server.name,
      }),
    );
  return [...own, ...coffer];
}

/** The one file every own entry sits in, or null when they span several. */
export function singleSource(rows: readonly McpRow[]): string | null {
  const sources = new Set(rows.flatMap((row) => (row.owner === "own" ? [row.entry.source] : [])));
  return sources.size === 1 ? [...sources][0] : null;
}
