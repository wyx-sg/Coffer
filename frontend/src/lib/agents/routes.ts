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
  "memory",
  "sessions",
  "config",
] as const;
export type AgentTab = (typeof AGENT_TABS)[number];
export const DEFAULT_AGENT_TAB: AgentTab = "overview";

/** The supported types, in the Agents page's order. */
export const AGENT_TYPES: readonly AgentType[] = ["claude_code", "codex"];

export function isAgentType(value: string | undefined): value is AgentType {
  return value !== undefined && (AGENT_TYPES as readonly string[]).includes(value);
}

const enc = encodeURIComponent;

export function agentBasePath(type: string): string {
  return `/agents/${enc(type)}`;
}

/** The canonical address of one tab (`/agents/<type>` for Overview). */
export function agentTabPath(type: string, tab: AgentTab, search = ""): string {
  return detailTabPath(agentBasePath(type), tab, AGENT_TABS, DEFAULT_AGENT_TAB, search);
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
