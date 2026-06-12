// frontend/src/components/knowledge_base/KnowledgeBasesTable.tsx
// The knowledge-bases list rendered via the shared DataTable (mirrors
// SkillsTable): rows navigate to the KB detail page, search covers name +
// description, and a modes column shows the enabled retrieval modes.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import type { KnowledgeBaseOut } from "@/kinds/knowledge_base/api";

function modesOf(row: KnowledgeBaseOut): string[] {
  const modes = (row.config as { enabled_modes?: unknown } | undefined)?.enabled_modes;
  if (Array.isArray(modes) && modes.length > 0) {
    return modes.filter((m): m is string => typeof m === "string");
  }
  return ["keyword", "grep"];
}

export function KnowledgeBasesTable({ items }: { items: KnowledgeBaseOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const del = useDeleteResource();

  const columns: Column<KnowledgeBaseOut>[] = [
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
      key: "docs",
      header: t("knowledgeBases.cols.docs"),
      className: "tabular-nums",
      cell: (r) => <span className="text-muted-foreground">{r.document_count ?? 0}</span>,
    },
    {
      key: "description",
      header: t("knowledgeBases.cols.description"),
      cell: (r) => <span className="text-muted-foreground">{r.description || "—"}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (r) => (
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm(t("knowledgeBases.deleteConfirm", { name: r.name }))) {
              del.mutate(
                { kind: "knowledge_base", name: r.name },
                { onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge-bases"] }) },
              );
            }
          }}
          aria-label={t("common.delete")}
        >
          <Trash2 className="size-4" />
        </Button>
      ),
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
