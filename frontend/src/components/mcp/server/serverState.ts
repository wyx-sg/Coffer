// src/components/mcp/server/serverState.ts — what state an MCP server is in, and the words for it, from its row and its status read.
//
// One derivation for the list's groups and reasons and the server pane's pill
// and callout, so the two never disagree (design 4.1: the list is grouped by
// what needs the user — failing, launcher missing, secret missing — then
// healthy, not checked yet, and off). Off wins, because a server no agent can
// use needs nothing until it is turned on; then a missing launcher and a
// missing secret, which name their cause; then the health word.
import type { StatusTone } from "@/components/status/statusTone";
import type { ResourceOut } from "@/lib/api/resources";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { InvocationSummary, ToolTiering } from "@/lib/hooks/useMcpServerPage";

type ServerStateKind =
  | "failing"
  | "launcherMissing"
  | "secretMissing"
  | "healthy"
  | "unknown"
  | "off";

export type ServerGroup = "attention" | "healthy" | "unknown" | "off";

export const GROUP_ORDER: readonly ServerGroup[] = ["attention", "healthy", "unknown", "off"];

export interface ServerState {
  kind: ServerStateKind;
  group: ServerGroup;
  tone: StatusTone;
}

const GROUP: Record<ServerStateKind, ServerGroup> = {
  failing: "attention",
  launcherMissing: "attention",
  secretMissing: "attention",
  healthy: "healthy",
  unknown: "unknown",
  off: "off",
};

const TONE: Record<ServerStateKind, StatusTone> = {
  failing: "err",
  launcherMissing: "warn",
  secretMissing: "warn",
  healthy: "ok",
  unknown: "off",
  off: "off",
};

export function serverState(
  resource: Pick<ResourceOut, "enabled">,
  detail: McpStatusDetail | null | undefined,
): ServerState {
  let kind: ServerStateKind;
  if (!resource.enabled) kind = "off";
  else if (detail?.missing_runner) kind = "launcherMissing";
  else if (detail?.missing_secret) kind = "secretMissing";
  else if (detail?.status === "failing") kind = "failing";
  else if (detail?.status === "healthy") kind = "healthy";
  else kind = "unknown";
  return { kind, group: GROUP[kind], tone: TONE[kind] };
}

export interface Transport {
  type: "stdio" | "http" | "unknown";
  /** The command line, or the URL. */
  target: string;
  /** The launcher alone (`npx`, `uvx`), for stdio. */
  command: string | null;
}

/** The transport a server's config names, for its subline. */
export function transportOf(config: unknown): Transport {
  const transport = (config as { transport?: Record<string, unknown> } | null)?.transport;
  if (!transport || typeof transport !== "object")
    return { type: "unknown", target: "", command: null };
  if (transport.type === "stdio") {
    const command = typeof transport.command === "string" ? transport.command : "";
    const args = Array.isArray(transport.args) ? transport.args.map(String) : [];
    return { type: "stdio", target: [command, ...args].join(" ").trim(), command: command || null };
  }
  if (transport.type === "http") {
    return {
      type: "http",
      target: typeof transport.url === "string" ? transport.url : "",
      command: null,
    };
  }
  return { type: "unknown", target: "", command: null };
}

/** A time the way the list says it: the clock time today, else the date and time. */
export function shortTime(iso: string, now = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const sameDay = at.toDateString() === now.toDateString();
  return sameDay
    ? at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : at.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/** The install line for a launcher Coffer knows how to name; null for the rest. */
export function installCommandFor(runner: string): string | null {
  const known: Record<string, string> = {
    uvx: "brew install uv",
    uv: "brew install uv",
    npx: "brew install node",
    node: "brew install node",
    bunx: "brew install oven-sh/bun/bun",
    bun: "brew install oven-sh/bun/bun",
    docker: "brew install --cask docker",
    deno: "brew install deno",
  };
  return known[runner] ?? null;
}

/** Each tool's last-24-hours calls and errors, by its original name. */
export function usageByTool(summary: InvocationSummary | undefined) {
  return new Map(
    (summary?.by_tool ?? []).map((row) => [row.tool, { calls: row.calls, errors: row.errors }]),
  );
}

export function listingOf(tiering: ToolTiering | null | undefined) {
  if (!tiering?.enabled || tiering.behind_search.length === 0) return null;
  return { listed: new Set(tiering.listed), behind: new Set(tiering.behind_search) };
}
