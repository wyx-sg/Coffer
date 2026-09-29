// src/lib/agents/routes.ts — every address under /agents, built in one place.
//
// An agent is one per type and named by it, so its pages are addressed by the
// TYPE (`/agents/claude_code`), never by its uid (spec agent-registry "Expose
// every agent operation through REST, CLI and the Agents page"). The detail
// page's tab is a path segment (`/agents/<type>/<tab>`, Overview at the bare
// path), and every page reached from a tab is nested under that tab, so its
// back link is the tab's address. REST routes are still keyed by uid; the
// type → uid step is `useAgentRoute` (lib/agents/useAgentRoute.ts).
import type { AgentType } from "@/lib/api/agents";
import { detailTabPath } from "@/lib/detailTabs";

/** The nine detail tabs, in the order the page shows them. The value is the path segment. */
export const AGENT_TABS = [
  "overview",
  "model",
  "skills",
  "mcp-servers",
  "plugins",
  "hooks",
  "config",
  "memory",
  "sessions",
] as const;
export type AgentTab = (typeof AGENT_TABS)[number];
export const DEFAULT_AGENT_TAB: AgentTab = "overview";

/** The supported types, in the Agents page's order. */
export const AGENT_TYPES: readonly AgentType[] = ["claude_code", "codex"];

export function isAgentType(value: string | undefined): value is AgentType {
  return value !== undefined && (AGENT_TYPES as readonly string[]).includes(value);
}

/** Old `?tab=` values (and the old Conversations segment) → today's tab. */
const LEGACY_TAB_ALIASES: Readonly<Record<string, AgentTab>> = {
  mcpServers: "mcp-servers",
  conversations: "sessions",
};

const enc = encodeURIComponent;

export function agentBasePath(type: string): string {
  return `/agents/${enc(type)}`;
}

/** The canonical address of one tab (`/agents/<type>` for Overview). */
export function agentTabPath(type: string, tab: AgentTab, search = ""): string {
  return detailTabPath(agentBasePath(type), tab, AGENT_TABS, DEFAULT_AGENT_TAB, search);
}

/** One direct MCP entry of the agent, under the MCP servers tab. */
export function agentMcpEntryPath(type: string, entry: string, source?: string): string {
  const qs = source ? `?source=${enc(source)}` : "";
  return `${agentBasePath(type)}/mcp-servers/${enc(entry)}${qs}`;
}

/** One installed plugin (`<name>@<marketplace>`, one encoded segment), under Plugins. */
export function agentPluginPath(type: string, pluginId: string): string {
  return `${agentBasePath(type)}/plugins/${enc(pluginId)}`;
}

/** One skill folder Coffer does not manage, named as the scan names it, under Skills. */
export function unmanagedSkillPath(type: string, location: string, name: string): string {
  return `${agentBasePath(type)}/skills/unmanaged/${enc(location)}/${enc(name)}`;
}

/** One native memory store, addressed by its directory (its identity), under Memory. */
export function agentMemoryStorePath(type: string, dir: string, project?: string | null): string {
  const params = new URLSearchParams({ dir });
  if (project) params.set("project", project);
  return `${agentBasePath(type)}/memory/store?${params.toString()}`;
}

/** The Sessions tab with one transcript open, addressed by its file (its identity). */
export function agentSessionPath(type: string, sessionPath: string): string {
  return `${agentTabPath(type, "sessions")}?${new URLSearchParams({ session: sessionPath })}`;
}

/**
 * Where an address in an older form belongs today, or `null` when it is
 * current. `rest` is the path after `/agents/<type>` (with its leading `/`, or
 * ""), `search` the query string. Covers the old `?tab=` values, the
 * Conversations tab (now Sessions, whose open session moved from the session
 * page's `?path=` to the tab's `?session=`), and a memory store opened from the
 * tab's own address (`/memory?dir=` → `/memory/store?dir=`).
 */
export function legacyAgentPath(type: string, rest: string, search: string): string | null {
  const params = new URLSearchParams(search);
  const queryTab = params.get("tab");
  const segments = rest.split("/").filter(Boolean);

  if (segments.length === 1 && segments[0] === "conversations") {
    const session = params.get("path");
    return session ? agentSessionPath(type, session) : agentTabPath(type, "sessions");
  }
  if (segments.length === 1 && segments[0] === "memory" && params.get("dir")) {
    return agentMemoryStorePath(type, params.get("dir") ?? "", params.get("project"));
  }
  if (segments.length === 0 && queryTab !== null && queryTab in LEGACY_TAB_ALIASES) {
    params.delete("tab");
    const other = params.toString();
    return agentTabPath(type, LEGACY_TAB_ALIASES[queryTab], other ? `?${other}` : "");
  }
  return null;
}
