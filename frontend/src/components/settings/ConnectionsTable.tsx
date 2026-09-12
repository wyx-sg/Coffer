// frontend/src/components/settings/ConnectionsTable.tsx
//
// The LLM-connection library rendered via the shared DataTable (mirrors
// SkillsTable / AgentTable), replacing the hand-rolled card list this surface
// used to be: search over name + endpoint + description, filters on vendor and
// enabled state, a per-row enable Switch, bulk enable/disable/delete,
// and pagination — all from DataTable. A row click opens the connection's detail
// page, where the endpoint is edited and its model set curated; the row itself
// carries only what a table row should.
//
// Which connection Coffer's own internal engine happens to run on is NOT one of
// those things, so no internal-engine badge here: this page manages providers,
// and that flag is a fact about the engine. It is set (and shown) where it
// belongs — the internal-engine settings panel, and the connection's own detail
// header.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import {
  ConnectionRowActions,
  ConnectionStatusCell,
  ConnectionsBulkActions,
} from "@/components/settings/ConnectionsTableActions";
import { AGENT_LABEL_KEY, PRESETS, vendorOf } from "@/components/settings/connectionPresets";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { Provider } from "@/lib/api/providers";
import { useDeleteProvider } from "@/lib/hooks/useProviders";

export function ConnectionsTable({ providers }: { providers: Provider[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteProvider();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null);

  // A preset's label is the vendor's own brand name, identical in every locale;
  // only the Custom fallback is a word we have to translate.
  const vendorLabel = (id: string, label: string) =>
    id === "custom" ? t("settings.connections.customProvider") : label;

  const columns: Column<Provider>[] = [
    {
      key: "name",
      header: t("settings.connections.name"),
      cell: (p) => (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{p.name}</span>
          {p.is_active ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
              <Check className="size-3" />
              {t("settings.connections.active")}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "vendor",
      header: t("settings.connections.provider"),
      className: "whitespace-nowrap",
      cell: (p) => {
        const vendor = vendorOf(p.base_url);
        return (
          <span className="text-muted-foreground">{vendorLabel(vendor.id, vendor.label)}</span>
        );
      },
    },
    {
      key: "base_url",
      header: t("settings.connections.baseUrl"),
      cell: (p) => <span className="line-clamp-1 max-w-xs font-mono text-xs">{p.base_url}</span>,
    },
    {
      key: "compatible_agents",
      header: t("settings.connections.compatibleAgents"),
      cell: (p) => (
        <div className="flex flex-wrap gap-1">
          {(p.compatible_agents ?? []).length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            (p.compatible_agents ?? []).map((a) => (
              <span
                key={a}
                className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                {t(AGENT_LABEL_KEY[a])}
              </span>
            ))
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "text-right",
      cell: (p) => <ConnectionStatusCell provider={p} />,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (p) => (
        <ConnectionRowActions
          provider={p}
          deleteDisabled={del.isPending}
          onDelete={() => setDeleteTarget(p)}
        />
      ),
    },
  ];

  const filters: FilterDef<Provider>[] = [
    {
      key: "vendor",
      label: t("settings.connections.provider"),
      allLabel: t("settings.connections.allVendors"),
      accessor: (p) => vendorOf(p.base_url).id,
      // The presets ARE the vendor vocabulary, Custom included — deriving the
      // options from them keeps the filter in step with the add-connection form.
      options: PRESETS.map((p) => ({ value: p.id, label: vendorLabel(p.id, p.label) })),
    },
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      accessor: (p) => (p.enabled ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <>
      <DataTable
        rows={providers}
        columns={columns}
        rowKey={(p) => p.name}
        search={{
          accessor: (p) => `${p.name} ${p.base_url} ${p.description ?? ""}`,
          placeholder: t("settings.connections.searchPlaceholder"),
        }}
        filters={filters}
        onRowClick={(p) => navigate(`/model-providers/${p.name}`)}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (p) => `${t("common.bulk.selectRow")}: ${p.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <ConnectionsBulkActions providers={selectedRows} onDone={clear} />
          ),
        }}
        emptyMessage={t("settings.connections.empty")}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("settings.connections.deleteTitle")}
        description={t("settings.connections.deleteConfirm", { name: deleteTarget?.name ?? "" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (deleteTarget) {
            del.mutate(deleteTarget.name, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
      />
    </>
  );
}
