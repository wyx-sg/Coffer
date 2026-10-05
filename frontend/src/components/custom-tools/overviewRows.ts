// src/components/custom-tools/overviewRows.ts — a group as an MCP server's Overview and Tools tab read it: its tools as
// tool rows (24-hour use, listed or behind search, the person's exposure), and its secret headers as Requires rows.
import type { CustomToolGroup, CustomToolHeaderOut } from "@/lib/api/customTools";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import type { ToolTiering } from "@/lib/hooks/useMcpServerPage";
import { listingOf } from "@/lib/mcp/serverState";
import { CLIENT_NAME_LIMIT } from "@/components/mcp/capabilityRows";
import type { ToolRow } from "@/components/mcp/server/toolRows";

type Requirement = McpStatusDetail["requires"][number];

/** The group's tools as tool rows; an Off group counts no use. */
export function groupToolRows(
  group: CustomToolGroup,
  tiering: ToolTiering | null | undefined,
): ToolRow[] {
  const listing = listingOf(tiering);
  const exposure = new Map((tiering?.tools ?? []).map((e) => [e.tool, e]));
  return group.tools.map((tool) => {
    const clientName = `mcp__coffer__${tool.agent_name}`;
    return {
      key: tool.name,
      prefixed: tool.agent_name,
      description: tool.description || `${tool.method} ${tool.path}`,
      enabled: tool.enabled,
      calls: group.enabled ? tool.calls_24h : null,
      errors: group.enabled ? tool.failures_24h : null,
      lastCallAt: null,
      listing: listing
        ? listing.behind.has(tool.name)
          ? "behind"
          : listing.listed.has(tool.name)
            ? "listed"
            : null
        : null,
      exposure: tiering?.enabled ? (exposure.get(tool.name) ?? null) : null,
      params: [],
      clientName,
      clientNameLength: clientName.length,
      tooLong: clientName.length > CLIENT_NAME_LIMIT,
    };
  });
}

const STATUS: Partial<Record<CustomToolHeaderOut["secret_state"], Requirement["status"]>> = {
  present: "set",
  missing: "missing",
  pending_approval: "waiting_approval",
};

/** What the group needs from this Mac: each secret its headers cite. Nothing runs here, so no launcher. */
/** The secrets a group's headers cite, one row per environment's secret header. With
 *  several environments a row is named `<environment> · <header>`. */
export function groupRequires(group: CustomToolGroup): Requirement[] {
  const envs = group.environments ?? [];
  const several = envs.length > 1;
  const sources = envs.length ? envs : [{ name: "", headers: group.headers }];
  return sources.flatMap((env) =>
    env.headers.flatMap((h) => {
      const status = h.secret ? STATUS[h.secret_state] : undefined;
      const name = several ? `${env.name} · ${h.name}` : h.name;
      return h.secret && status
        ? [{ kind: "secret" as const, name, secret: h.secret, status, version: null }]
        : [];
    }),
  );
}
