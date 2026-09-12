// frontend/src/components/knowledge/KnowledgeTable.tsx
// The collections list, rendered via the shared DataTable. A collection is a
// top-level folder under the knowledge root and one `knowledge` Resource, so a
// row carries only what a folder has: its name, what its README says it is for,
// and how many markdown files are under it.
//
// Deleting goes through the kind-agnostic resource route, which cascades the
// directory — collection lifecycle is a Resource concern, not a knowledge one.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { collectionsKey } from "@/kinds/knowledge/useKnowledge";
import type { CollectionOut } from "@/kinds/knowledge/types";

export function KnowledgeTable({ items }: { items: CollectionOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const del = useDeleteResource();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const columns: Column<CollectionOut>[] = [
    {
      key: "name",
      header: t("knowledge.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "files",
      header: t("knowledge.cols.files"),
      cell: (r) => <span className="tabular-nums">{r.file_count}</span>,
    },
    {
      key: "description",
      header: t("knowledge.cols.description"),
      cell: (r) => (
        <span className="text-sm text-muted-foreground">{r.description ?? ""}</span>
      ),
    },
    {
      key: "actions",
      header: "",
      cell: (r) => (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t("common.delete")}
          onClick={(e) => {
            e.stopPropagation();
            setDeletingName(r.name);
          }}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      ),
    },
  ];

  return (
    <>
      <DataTable
        rows={items}
        columns={columns}
        rowKey={(r) => r.name}
        onRowClick={(r) => navigate(`/knowledge/${encodeURIComponent(r.name)}`)}
        search={{
          accessor: (r) => `${r.name} ${r.description ?? ""}`,
          placeholder: t("knowledge.searchPlaceholder"),
        }}
        emptyMessage={t("knowledge.empty")}
      />
      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingName(null);
        }}
        title={t("knowledge.delete.title")}
        description={t("knowledge.delete.description", { name: deletingName ?? "" })}
        confirmLabel={t("common.delete")}
        variant="destructive"
        onConfirm={() => {
          const name = deletingName;
          setDeletingName(null);
          if (name === null) return;
          del.mutate(
            { kind: "knowledge", name },
            { onSuccess: () => void qc.invalidateQueries({ queryKey: collectionsKey() }) },
          );
        }}
      />
    </>
  );
}
