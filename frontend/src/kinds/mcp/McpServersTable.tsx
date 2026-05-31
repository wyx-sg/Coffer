// frontend/src/kinds/mcp/McpServersTable.tsx
//
// The MCP servers list rendered via the shared DataTable (matching the
// Agents/Skills tables): name + transport + health + description + an
// enable/disable Switch + a delete action, with row multi-select driving bulk
// enable/disable/delete. A row click opens the server's detail page; the inline
// controls stop propagation so they don't trigger it.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import {
  McpServersBulkActions,
  ServerDeleteCell,
  ServerHealthCell,
  ServerStatusCell,
} from "./McpServersTableCells";

function transportType(r: ResourceOut): string {
  const tr = (r.config as Record<string, unknown> | undefined)?.transport;
  if (tr && typeof tr === "object" && typeof (tr as Record<string, unknown>).type === "string") {
    return (tr as Record<string, unknown>).type as string;
  }
  return "unknown";
}

export function McpServersTable({ resources }: { resources: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "transport",
      header: t("resources.cols.transport"),
      className: "whitespace-nowrap",
      cell: (r) => <Badge variant="secondary">{transportType(r)}</Badge>,
    },
    {
      key: "health",
      header: t("resources.cols.health"),
      className: "whitespace-nowrap",
      cell: (r) => <ServerHealthCell name={r.name} />,
    },
    {
      // The flexible column: takes the remaining width so a long description
      // wraps to a couple of lines instead of squeezing the others.
      key: "description",
      header: t("resources.cols.description"),
      className: "w-full min-w-[16rem]",
      cell: (r) => (
        <span className="line-clamp-2 text-muted-foreground">{r.description || "—"}</span>
      ),
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <ServerStatusCell resource={r} />,
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) => <ServerDeleteCell resource={r} />,
    },
  ];

  const filters: FilterDef<ResourceOut>[] = [
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      accessor: (r) => (r.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <DataTable
      rows={resources}
      columns={columns}
      rowKey={(r) => r.name}
      search={{
        accessor: (r) => `${r.name} ${transportType(r)}`,
        placeholder: t("mcp.table.search"),
      }}
      filters={filters}
      onRowClick={(r) => navigate(`/mcp-servers/mcp_server/${r.name}`)}
      selection={{
        ariaSelectAll: t("common.bulk.selectAll"),
        ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
        bulkLabel: (count) => t("common.bulk.selected", { count }),
        clearLabel: t("common.clear"),
        renderBulkActions: ({ selectedRows, clear }) => (
          <McpServersBulkActions rows={selectedRows} onDone={clear} />
        ),
      }}
      emptyMessage={t("resources.noMatches")}
    />
  );
}
