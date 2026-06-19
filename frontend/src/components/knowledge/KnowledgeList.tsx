// frontend/src/components/knowledge/KnowledgeList.tsx
// The intermixed notes + documents list for one scope (FR-017b), rendered via
// the shared DataTable: a type column (icon + 笔记/文档 tag), title, source, and
// updated-at, with a free-text search and a type filter. Clicking a row opens
// the read-only viewer. Notes and documents sit together, distinguished only by
// their type tag — the two kinds, presented not merged.
import { useTranslation } from "react-i18next";
import { FileText, Lock, StickyNote } from "lucide-react";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import type { KnowledgeItem } from "@/lib/api/knowledge";

interface Props {
  items: KnowledgeItem[];
  onSelect: (item: KnowledgeItem) => void;
}

export function KnowledgeList({ items, onSelect }: Props) {
  const { t } = useTranslation();

  const typeTag = (item: KnowledgeItem) => {
    const Icon = item.type === "note" ? StickyNote : FileText;
    return (
      <span className="inline-flex items-center gap-1.5">
        <Icon className="size-3.5 text-muted-foreground" />
        <Badge variant="secondary" className="rounded-sm">
          {t(`knowledge.type.${item.type}`)}
        </Badge>
      </span>
    );
  };

  const columns: Column<KnowledgeItem>[] = [
    {
      key: "type",
      header: t("knowledge.cols.type"),
      cell: typeTag,
    },
    {
      key: "title",
      header: t("knowledge.cols.title"),
      cell: (item) => (
        <div className="min-w-0">
          <span className="flex items-center gap-1.5 font-medium">
            <span className="truncate">{item.title || t("knowledge.untitled")}</span>
            {item.locked ? <Lock className="size-3 shrink-0 text-status-warn" /> : null}
          </span>
          {item.preview ? (
            <span className="block truncate text-xs text-muted-foreground">{item.preview}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: "source",
      header: t("knowledge.cols.source"),
      cell: (item) => (
        <span className="text-xs text-muted-foreground">
          {item.type === "note" ? t("knowledge.source.note") : item.kbName}
        </span>
      ),
    },
  ];

  const filters: FilterDef<KnowledgeItem>[] = [
    {
      key: "type",
      label: t("knowledge.cols.type"),
      allLabel: t("knowledge.filter.allTypes"),
      accessor: (item) => item.type,
      options: [
        { value: "note", label: t("knowledge.type.note") },
        { value: "document", label: t("knowledge.type.document") },
      ],
    },
  ];

  return (
    <DataTable
      rows={items}
      columns={columns}
      rowKey={(item) => item.ref}
      search={{
        accessor: (item) => `${item.title} ${item.preview} ${item.kbName ?? ""}`,
        placeholder: t("knowledge.searchPlaceholder"),
      }}
      filters={filters}
      onRowClick={onSelect}
      emptyMessage={t("knowledge.empty")}
    />
  );
}
