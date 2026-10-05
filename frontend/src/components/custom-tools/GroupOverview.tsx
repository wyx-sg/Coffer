// src/components/custom-tools/GroupOverview.tsx — a group's Overview tab: its definition, then what an MCP server's
// Overview shows (spec web-ui "Manage custom tool groups on their own page") — Last 24 hours with View in Activity,
// Requires (the secrets its headers cite; nothing is launched, so no CLI row) and the most-called tools.
import { SectionStack } from "@/components/Section";
import { McpLast24h } from "@/components/mcp/server/McpLast24h";
import { McpRequires } from "@/components/mcp/server/McpRequires";
import type { ToolRow } from "@/components/mcp/server/toolRows";
import type { AgentOut } from "@/lib/api/agents";
import type { CustomToolGroup } from "@/lib/api/customTools";
import type { InvocationSummary } from "@/lib/hooks/useMcpServerPage";
import { GroupDefinition } from "./GroupDefinition";
import { GroupTopTools } from "./GroupTopTools";
import { groupRequires } from "./overviewRows";

interface Props {
  group: CustomToolGroup;
  agents: readonly AgentOut[];
  summary: InvocationSummary | undefined;
  summaryPending: boolean;
  rows: readonly ToolRow[];
  toolsHref: string;
  onReimport: () => void;
}

export function GroupOverview({
  group,
  agents,
  summary,
  summaryPending,
  rows,
  toolsHref,
  onReimport,
}: Props) {
  return (
    <div className="flex flex-col gap-6">
      <GroupDefinition group={group} onReimport={onReimport} />
      <SectionStack>
        <McpLast24h
          name={group.name}
          enabled={group.enabled}
          agents={agents}
          summary={summary}
          summaryPending={summaryPending}
          activityHref={`/activity?tab=mcp&q=${encodeURIComponent(group.name)}`}
        />
        <McpRequires requires={groupRequires(group)} />
        <GroupTopTools name={group.name} rows={rows} toolsHref={toolsHref} />
      </SectionStack>
    </div>
  );
}
