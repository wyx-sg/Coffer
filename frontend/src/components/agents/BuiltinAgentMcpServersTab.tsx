// frontend/src/components/agents/BuiltinAgentMcpServersTab.tsx — spec 008.
// READ-ONLY list of the MCP servers Coffer's gateway aggregates for the
// built-in agent. Built-in agents reach every enabled server through the
// gateway, so there are no per-agent install controls — just the catalogue
// with a note. When the agent's gateway is off, tools are disabled, so we say
// so instead.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useResources } from "@/lib/hooks/useResources";

const MCP_KIND = "mcp_server";

export function BuiltinAgentMcpServersTab({
  agentName,
  useGateway,
}: {
  agentName: string;
  useGateway: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const resources = useResources(MCP_KIND);

  if (!useGateway) {
    return <p className="text-sm text-muted-foreground">{t("builtinAgents.detail.gatewayOff")}</p>;
  }

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

  // The servers the gateway exposes = Coffer's enabled mcp_server resources.
  const servers = (resources.data ?? []).filter((r) => r.kind === MCP_KIND && r.enabled);

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("builtinAgents.detail.mcpNote")}</p>

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
              state: { backTo: `/agents/builtin/${agentName}`, backLabel: agentName },
            })
          }
          emptyMessage={t("builtinAgents.detail.mcpEmpty")}
        />
      )}
    </div>
  );
}
