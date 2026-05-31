// frontend/src/components/agents/AgentMcpServersTab.tsx
// "MCP servers" tab on the agent detail page. When Coffer's MCP isn't installed
// on the agent, a muted info note explains the prerequisite (the install button
// lives in the page header). Once installed, a "Managed by Coffer" section
// lists the MCP servers Coffer currently exposes (its enabled mcp_server
// resources) as a READ-ONLY table — rows are clickable through to the server
// detail. There is intentionally no enable/disable toggle here: that would flip
// the server for all of Coffer, not just this agent. Per-agent control is a
// planned Layer-2 feature (per-(agent, server) grants); until then the
// Coffer-level toggle lives only on the MCP servers page.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useAgentMcpStatus } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

const MCP_KIND = "mcp_server";

export function AgentMcpServersTab({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const status = useAgentMcpStatus(agentName);
  const resources = useResources(MCP_KIND);

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "description",
      header: t("resources.cols.description"),
      cell: (r) =>
        r.description ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{r.description}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  if (status.isPending) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }

  if (!status.data?.installed) {
    return <p className="text-sm text-muted-foreground">{t("agents.mcpTab.notInstalled")}</p>;
  }

  // The servers Coffer currently exposes to this agent = its enabled servers.
  const servers = (resources.data ?? []).filter((r) => r.kind === MCP_KIND && r.enabled);

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">{t("agents.cofferManaged")}</h3>

      {resources.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : resources.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, resources.error)}</p>
      ) : (
        <DataTable
          rows={servers}
          columns={columns}
          rowKey={(r) => r.name}
          search={{ accessor: (r) => r.name, placeholder: t("mcp.table.search") }}
          onRowClick={(r) =>
            navigate(`/mcp-servers/mcp_server/${r.name}`, {
              state: { backTo: `/agents/${agentName}`, backLabel: agentName },
            })
          }
          emptyMessage={t("agents.mcpTab.empty")}
        />
      )}
    </div>
  );
}
