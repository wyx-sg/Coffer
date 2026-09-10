// frontend/src/components/knowledge/KnowledgeTable.tsx
// The knowledge-scopes list rendered via the shared DataTable — one table where
// there used to be two (memory stores + knowledge bases). Rows navigate to the
// scope detail page and search covers the readable label / path / name /
// description. There is NO scope column: the Name cell already reads `global`,
// a project's absolute path, or a collection's name, so a badge repeating that
// says nothing the row has not said.
//
// Notes and documents get their OWN columns. They are separate lanes of a
// scope — notes are what an agent or the user wrote, documents are what
// someone uploaded — so they are never summed into one "items" number.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { projectDirName, scopeDisplayName, type ScopeOut } from "@/kinds/knowledge/api";

export function KnowledgeTable({ items }: { items: ScopeOut[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const del = useDeleteResource();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);

  const columns: Column<ScopeOut>[] = [
    {
      key: "name",
      header: t("knowledge.cols.name"),
      // Readable identity: a user-set label, else the project_root basename,
      // else the scope's own name — never the opaque project-<ULID> as the
      // primary label, with a graceful "unnamed" placeholder for an orphan
      // project scope. The absolute path (or the raw name) shows muted beneath
      // so the row stays identifiable.
      cell: (r) => {
        const display = scopeDisplayName(r);
        return (
          <div className="min-w-0">
            <span className="font-medium">{display ?? t("knowledge.unnamedScope")}</span>
            {r.project_root ? (
              <span className="block truncate font-mono text-xs text-muted-foreground">
                {r.project_root}
              </span>
            ) : display === null ? (
              <span className="block truncate font-mono text-xs text-muted-foreground">
                {r.name}
              </span>
            ) : null}
          </div>
        );
      },
    },
    {
      key: "notes",
      header: t("knowledge.cols.notes"),
      className: "tabular-nums",
      cell: (r) => <span className="text-muted-foreground">{r.entry_count ?? 0}</span>,
    },
    {
      key: "documents",
      header: t("knowledge.cols.documents"),
      className: "tabular-nums",
      cell: (r) => <span className="text-muted-foreground">{r.document_count ?? 0}</span>,
    },
    {
      key: "description",
      header: t("knowledge.cols.description"),
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
          // Search the readable label + absolute path too, so users can find a
          // project scope by its directory name or path (not just the ULID).
          accessor: (r) =>
            `${r.label ?? ""} ${projectDirName(r.project_root) ?? ""} ${r.project_root ?? ""} ${r.name} ${r.description ?? ""}`,
          placeholder: t("knowledge.searchPlaceholder"),
        }}
        onRowClick={(r) => navigate(`/knowledge/${r.name}`)}
        emptyMessage={t("knowledge.noMatches")}
      />

      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(o) => !o && setDeletingName(null)}
        title={t("knowledge.deleteScopeConfirm", { name: deletingName ?? "" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        pending={del.isPending}
        onConfirm={() => {
          if (!deletingName) return;
          del.mutate(
            { kind: "knowledge", name: deletingName },
            {
              onSuccess: () => {
                qc.invalidateQueries({ queryKey: ["knowledge-scopes"] });
                setDeletingName(null);
              },
            },
          );
        }}
      />
    </>
  );
}
