// frontend/src/components/memory/MemoryStoresTable.tsx
// The memory-stores list rendered via the shared DataTable (mirrors
// KnowledgeBasesTable): rows navigate to the store detail page, search covers
// name + description, and an LLM-provider column shows how writes are handled.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import type { ResourceOut } from "@/lib/components/kindRegistry";

function providerOf(row: ResourceOut): string {
  return (row.config as { llm_provider?: string } | undefined)?.llm_provider ?? "none";
}

export function MemoryStoresTable({ items }: { items: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "provider",
      header: t("memory.cols.provider"),
      cell: (r) => (
        <span className="inline-flex rounded-full border border-border/60 bg-secondary px-2 py-0.5 text-xs">
          {providerOf(r)}
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
