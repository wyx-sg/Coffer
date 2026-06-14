// frontend/src/components/memory/MemoryStoresTable.tsx
// The memory-stores list rendered via the shared DataTable (mirrors
// KnowledgeBasesTable): rows navigate to the store detail page, search covers
// name + description, and a scope column distinguishes global vs per-project
// stores (stores are auto-provisioned; there is no llm_provider anymore).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { deriveScope, type MemoryStoreOut } from "@/kinds/memory/api";

export function MemoryStoresTable({ items }: { items: MemoryStoreOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const del = useDeleteResource();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  // The dedicated `/memory_stores` rows carry an explicit `scope`; fall back to
  // deriving it from project_id vs the WORKSPACE_GLOBAL sentinel, and only show
  // "unknown" when neither signal is present (never silently default to global).
  const scopeLabel = (row: MemoryStoreOut): string => {
    const scope = deriveScope(row);
    return scope ? t(`memory.scope.${scope}`) : t("memory.scope.unknown");
  };

  const columns: Column<MemoryStoreOut>[] = [
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
      key: "facts",
      header: t("memory.cols.facts"),
      className: "tabular-nums",
      cell: (r) => <span className="text-muted-foreground">{r.fact_count ?? 0}</span>,
    },
    {
      key: "description",
      header: t("memory.cols.description"),
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
            setDeletingName(r.name);
          }}
          aria-label={t("common.delete")}
        >
          <Trash2 className="size-4" />
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
        search={{
          accessor: (r) => `${r.name} ${r.description ?? ""}`,
          placeholder: t("memory.searchPlaceholder"),
        }}
        onRowClick={(r) => navigate(`/memory/${r.name}`)}
        emptyMessage={t("memory.noMatches")}
      />

      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(o) => !o && setDeletingName(null)}
        title={t("memory.deleteStoreConfirm", { name: deletingName ?? "" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (!deletingName) return;
          del.mutate(
            { kind: "memory", name: deletingName },
            {
              onSuccess: () => {
                qc.invalidateQueries({ queryKey: ["memory-stores"] });
                setDeletingName(null);
              },
            },
          );
        }}
      />
    </>
  );
}
