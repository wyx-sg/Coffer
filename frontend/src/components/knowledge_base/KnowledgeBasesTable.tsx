// frontend/src/components/knowledge_base/KnowledgeBasesTable.tsx
// The knowledge-bases list rendered via the shared DataTable (mirrors
// SkillsTable): rows navigate to the KB detail page, search covers name +
// description, and a modes column shows the enabled retrieval modes.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import type { ResourceOut } from "@/lib/components/kindRegistry";

function modesOf(row: ResourceOut): string[] {
  const modes = (row.config as { enabled_modes?: unknown } | undefined)?.enabled_modes;
  if (Array.isArray(modes) && modes.length > 0) {
    return modes.filter((m): m is string => typeof m === "string");
  }
  return ["keyword", "grep"];
}

export function KnowledgeBasesTable({ items }: { items: ResourceOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<ResourceOut>[] = [
    {
      key: "name",
      header: t("knowledgeBases.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "mode",
      header: t("knowledgeBases.cols.mode"),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          {modesOf(r).map((m) => (
            <span
              key={m}
              className="inline-flex rounded-full border border-border/60 bg-secondary px-2 py-0.5 text-xs"
            >
              {m}
            </span>
          ))}
        </span>
      ),
    },
    {
      key: "description",
      header: t("knowledgeBases.cols.description"),
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
        placeholder: t("knowledgeBases.searchPlaceholder"),
      }}
      onRowClick={(r) => navigate(`/knowledge-bases/${r.name}`)}
      emptyMessage={t("knowledgeBases.noMatches")}
    />
  );
}
