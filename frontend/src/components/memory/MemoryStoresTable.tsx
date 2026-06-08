// frontend/src/components/memory/MemoryStoresTable.tsx
// The memory-stores list rendered via the shared DataTable (mirrors
// KnowledgeBasesTable): rows navigate to the store detail page, search covers
// name + description, and a scope column distinguishes global vs per-project
// stores (stores are auto-provisioned; there is no llm_provider anymore).
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { deriveScope } from "@/kinds/memory/api";
import type { ResourceOut } from "@/lib/components/kindRegistry";

export function MemoryStoresTable({ items }: { items: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Derive scope from project_id vs the WORKSPACE_GLOBAL sentinel (or an
  // explicit scope) rather than silently defaulting to "global". Render an
  // explicit "unknown" label when neither signal is present.
  const scopeLabel = (row: ResourceOut): string => {
    const scope = deriveScope(row as Parameters<typeof deriveScope>[0]);
    return scope ? t(`memory.scope.${scope}`) : t("memory.scope.unknown");
  };

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "scope",
      header: t("memory.cols.scope"),
      cell: (r) => (
        <span className="inline-flex rounded-full border border-border/60 bg-secondary px-2 py-0.5 text-xs">
          {scopeLabel(r)}
        </span>
      ),
    },
    {
      key: "description",
      header: t("memory.cols.description"),
      cell: (r) => <span className="text-muted-foreground">{r.description || "—"}</span>,
    },
  ];

  return (
    <DataTable
      rows={items}
      columns={columns}
      rowKey={(r) => r.name}
      search={{
        accessor: (r) => `${r.name} ${r.description ?? ""}`,
        placeholder: t("memory.searchPlaceholder"),
      }}
      onRowClick={(r) => navigate(`/memory/${r.name}`)}
      emptyMessage={t("memory.noMatches")}
    />
  );
}
