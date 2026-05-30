// frontend/src/kinds/mcp/McpServersTable.tsx
//
// The MCP servers list rendered with the shared DataTable (unified with the
// Agents surface): search + status filter + pagination, a row click opens the
// server's detail page, and the only inline row action is a delete icon. The
// per-row health badge + enable toggle reuse the same hooks the card did.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { ResourceOut } from "@/lib/components/kindRegistry";
import { useMcpServerStatus } from "@/lib/hooks/useMcpInvocations";
import {
  useDeleteResource,
  useDisableResource,
  useEnableResource,
} from "@/lib/hooks/useResourceMutations";
import { HealthBadge } from "./HealthBadge";
import { McpServerDeleteDialog } from "./McpServerDeleteDialog";

function transportType(r: ResourceOut): string {
  const tr = (r.config as Record<string, unknown> | undefined)?.transport;
  if (tr && typeof tr === "object" && typeof (tr as Record<string, unknown>).type === "string") {
    return (tr as Record<string, unknown>).type as string;
  }
  return "—";
}

function HealthCell({ name }: { name: string }) {
  const { data: status } = useMcpServerStatus(name);
  return status ? (
    <HealthBadge state={status} />
  ) : (
    <span className="text-xs text-muted-foreground">—</span>
  );
}

function EnabledToggle({ resource }: { resource: ResourceOut }) {
  const { t } = useTranslation();
  const enable = useEnableResource();
  const disable = useDisableResource();
  return (
    <Switch
      checked={resource.enabled}
      disabled={enable.isPending || disable.isPending}
      aria-label={resource.enabled ? t("common.enabled") : t("common.disabled")}
      onClick={(e) => e.stopPropagation()}
      onCheckedChange={(checked) =>
        (checked ? enable : disable).mutate({ kind: resource.kind, name: resource.name })
      }
    />
  );
}

export function McpServersTable({ resources }: { resources: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteResource();
  const [deleting, setDeleting] = useState<ResourceOut | null>(null);

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("agents.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "transport",
      header: t("mcp.table.transport"),
      cell: (r) => <Badge variant="secondary">{transportType(r)}</Badge>,
    },
    { key: "health", header: t("mcp.table.health"), cell: (r) => <HealthCell name={r.name} /> },
    {
      key: "enabled",
      header: t("agents.status"),
      cell: (r) => <EnabledToggle resource={r} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (r) => (
        <Button
          variant="ghost"
          size="icon"
          className="size-8 text-muted-foreground hover:text-destructive"
          aria-label={t("mcp.table.deleteAria", { name: r.name })}
          onClick={(e) => {
            e.stopPropagation();
            setDeleting(r);
          }}
        >
          <Trash2 className="size-4" />
        </Button>
      ),
    },
  ];

  const filters: FilterDef<ResourceOut>[] = [
    {
      key: "status",
      label: t("agents.status"),
      allLabel: t("resources.status.all"),
      accessor: (r) => (r.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <>
      <DataTable
        rows={resources}
        columns={columns}
        rowKey={(r) => r.name}
        search={{
          accessor: (r) => `${r.name} ${transportType(r)}`,
          placeholder: t("mcp.table.search"),
        }}
        filters={filters}
        onRowClick={(r) => navigate(`/resources/mcp_server/${r.name}`)}
        emptyMessage={t("resources.noMatches")}
      />
      <McpServerDeleteDialog
        name={deleting?.name ?? ""}
        open={deleting !== null}
        isPending={del.isPending}
        onOpenChange={(o) => !o && setDeleting(null)}
        onConfirm={() =>
          deleting &&
          del.mutate(
            { kind: "mcp_server", name: deleting.name },
            { onSuccess: () => setDeleting(null) },
          )
        }
      />
    </>
  );
}
