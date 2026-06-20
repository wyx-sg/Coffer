// frontend/src/components/agents/AgentGatewayMcpSection.tsx — spec 004.
// Section A of the agent "MCP servers" tab: Coffer's shim install status (the
// install button lives in the page header) plus the READ-ONLY list of MCP
// servers Coffer currently exposes through the gateway (its enabled
// mcp_server resources). Rows click through to the server detail. Extracted
// from AgentMcpServersTab to keep that file inside the component size cap.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useAgentMcpStatus } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

const MCP_KIND = "mcp_server";

export function AgentGatewayMcpSection({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const status = useAgentMcpStatus(agentName);
  const resources = useResources(MCP_KIND);

  const gatewayColumns: Column<ResourceOut>[] = [
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

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">
        {t("agents.workspace.mcp.gatewayTitle")}
      </h3>
      {status.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : !status.data?.installed ? (
        <p className="text-sm text-muted-foreground">{t("agents.mcpTab.notInstalled")}</p>
      ) : resources.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : resources.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, resources.error)}</p>
      ) : (
        <DataTable
          // The servers Coffer exposes to this agent = its enabled servers.
          rows={(resources.data ?? []).filter((r) => r.kind === MCP_KIND && r.enabled)}
          columns={gatewayColumns}
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
    </section>
  );
}
