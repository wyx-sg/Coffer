// frontend/src/components/settings/ConnectionsTable.tsx
//
// The LLM-connection library rendered via the shared DataTable (mirrors
// SkillsTable / AgentTable), replacing the hand-rolled card list this surface
// used to be: search over name + endpoint + description, filters on vendor and
// reach, the per-row three-state reach control, a bulk bar carrying that same
// control plus delete, and pagination — all from DataTable. A row click opens
// the connection's detail page, where the endpoint is edited and its model set
// curated; the row itself carries only what a table row should.
//
// Which connection Coffer's own internal engine happens to run on is NOT one of
// those things, so no internal-engine badge here: this page manages providers,
// and that flag is a fact about the engine. It is set (and shown) where it
// belongs — the internal-engine settings panel, and the connection's own detail
// header.
//
// Transcription is the one exception, and for a reason that does not generalise:
// it has NO fallback. Exactly one connection carries speech-to-text, every voice
// message goes to that endpoint, and no connection carrying it means Coffer
// transcribes nothing at all — so "which one?" is a question the library itself
// must answer. The pill is read-only; it is still set in Settings → Engine,
// beside the engine's own connection.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { ActiveProviderBadge } from "@/components/settings/ActiveProviderBadge";
import { TranscribeProviderBadge } from "@/components/settings/TranscribeProviderBadge";
import {
  ConnectionRowActions,
  ConnectionStatusCell,
  ConnectionsBulkActions,
  PROVIDER_KIND,
} from "@/components/settings/ConnectionsTableActions";
import { PRESETS, vendorOf } from "@/components/settings/connectionPresets";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { Provider } from "@/lib/api/providers";
import { useDeleteProvider } from "@/lib/hooks/useProviders";
import { useKindReach } from "@/lib/hooks/useResources";
import { reachFilter } from "@/lib/reachFilter";

export function ConnectionsTable({
  providers,
  isLoading = false,
}: {
  providers: Provider[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteProvider();
  // `scope` is a generic Resource field, absent from the /providers payload, so
  // it comes from ONE extra list request rather than one GET per row.
  const reach = useKindReach(PROVIDER_KIND);
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
          {p.is_active ? <ActiveProviderBadge /> : null}
          {p.transcribe_default ? <TranscribeProviderBadge /> : null}
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
      // The column IS the reach control, so it is named for what it shows.
      // Which agents the provider projects into is that same reach, so there is
      // no separate compatible-agents column repeating it in words.
      key: "reach",
      header: t("resources.cols.reach"),
      className: "whitespace-nowrap text-right",
      cell: (p) => <ConnectionStatusCell provider={p} reach={reach.get(p.name)} />,
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
    // The one reach filter every scoped list offers; `scope` is merged in from
    // the kind-wide reach query rather than carried on the provider row.
    reachFilter(t, (p) => ({ enabled: p.enabled, scope: reach.get(p.name)?.scope })),
  ];

  return (
    <>
      <DataTable
        rows={providers}
        columns={columns}
        rowKey={(p) => p.name}
        isLoading={isLoading}
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
