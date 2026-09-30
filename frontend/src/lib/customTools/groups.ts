// src/lib/customTools/groups.ts — pure helpers the Custom tools page shares: which
// `mcp_server` is a group, how groups are sectioned by health, and short labels.
import type { StatusTone } from "@/components/status/statusTone";
import type { CustomTool, CustomToolGroup, GroupHealth, HttpMethod } from "@/lib/api/customTools";

/** The transport a custom-tool group's `mcp_server` carries. */
const HTTP_API_TRANSPORT = "http_api";

/**
 * Whether an `mcp_server` resource is a custom-tool group — its
 * `config.transport.type` is `http_api`. The MCP servers page leaves these out
 * and its detail route sends them to `/custom-tools/<name>`.
 */
export function isCustomToolGroup(resource: { config?: unknown }): boolean {
  const config = resource.config;
  if (typeof config !== "object" || config === null) return false;
  const transport = (config as { transport?: unknown }).transport;
  if (typeof transport !== "object" || transport === null) return false;
  return (transport as { type?: unknown }).type === HTTP_API_TRANSPORT;
}

/** The three sections of the list, in the order they are shown. */
export type GroupSection = "attention" | "healthy" | "off";
const GROUP_SECTIONS: readonly GroupSection[] = ["attention", "healthy", "off"];

const SECTION_OF: Record<GroupHealth, GroupSection> = {
  failing: "attention",
  attention: "attention",
  healthy: "healthy",
  idle: "healthy",
  off: "off",
};

/** Failing before attention, healthy before idle — the daemon's own order. */
const HEALTH_RANK: Record<GroupHealth, number> = {
  failing: 0,
  attention: 1,
  healthy: 2,
  idle: 3,
  off: 4,
};

function sectionOf(health: GroupHealth): GroupSection {
  return SECTION_OF[health];
}

/** The groups matching `filter` (name, host or a tool name), split into the
 *  sections that have any, failing first. */
export function sectionGroups(
  groups: readonly CustomToolGroup[],
  filter: string,
): { section: GroupSection; groups: CustomToolGroup[] }[] {
  const q = filter.trim().toLowerCase();
  const matching = groups.filter(
    (g) =>
      !q ||
      g.name.toLowerCase().includes(q) ||
      hostOf(g.base_url).toLowerCase().includes(q) ||
      g.tools.some((tool) => tool.name.toLowerCase().includes(q)),
  );
  const sorted = [...matching].sort(
    (a, b) => HEALTH_RANK[a.health] - HEALTH_RANK[b.health] || a.name.localeCompare(b.name),
  );
  return GROUP_SECTIONS.map((section) => ({
    section,
    groups: sorted.filter((g) => sectionOf(g.health) === section),
  })).filter((s) => s.groups.length > 0);
}

/** The status tone a group's health reads in. */
export function healthTone(health: GroupHealth): StatusTone {
  if (health === "failing") return "err";
  if (health === "attention") return "warn";
  if (health === "off") return "off";
  return "ok";
}

/** A base URL's host, for the list row; the URL itself when it does not parse. */
export function hostOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl;
  }
}

/** A method changes data unless it is GET — the flag's default. */
export function changesDataByDefault(method: HttpMethod): boolean {
  return method !== "GET";
}

/** How many of a group's tools are switched on. */
export function toolsOn(tools: readonly CustomTool[]): number {
  return tools.filter((tool) => tool.enabled).length;
}

/** The agents-see name for a group, with `<tool>` standing in for any tool. */
export function agentPrefix(group: string): string {
  return `${group}__<tool>`;
}

/** A group's reach in the scope shape the reach vocabulary reads. */
export function groupScope(group: CustomToolGroup): { agents: string[] } | null {
  return group.scope === null ? null : { agents: group.scope };
}
