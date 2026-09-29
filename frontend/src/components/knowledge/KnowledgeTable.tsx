// frontend/src/components/knowledge/KnowledgeTable.tsx
// The collections list, rendered via the shared DataTable. A collection is a
// top-level folder under the knowledge root and one `knowledge` Resource, so a
// row carries what a folder has — its name, what its README says it is for, how
// many documents it holds and how much material is waiting to be merged into
// them — and nothing else.
//
// There is NO status or reach column and no bulk enable / disable. The
// `knowledge` kind declares itself non-toggleable: every collection is served
// to every agent (spec knowledge "Serve every collection to every agent"), so a
// control there would offer a choice with nothing behind it (spec web-ui "Show
// reach as a labelled button on every list and detail page").
//
// Documents and pending material are counted APART because they answer
// different questions: how much an agent can read today, and how much is still
// in the inbox where no agent can see it. A collection with material pending
// is one curation has not caught up with, which a single total would hide
// (spec knowledge "Hide dot-prefixed entries except the inbox").
//
// Deleting goes through the kind-agnostic resource route, which cascades the
// directory — collection lifecycle is a Resource concern, not a knowledge one.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { DataTable, type Column } from "@/components/DataTable";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { resourcesApi } from "@/lib/api/resources";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { knowledgeCollectionsKey, resourcesKey } from "@/lib/api/queryKeys";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";
import { displayName, searchableName } from "@/lib/resourceTitle";
import { ResourceLabel } from "@/components/resource/ResourceLabel";

const KIND = "knowledge";

export function KnowledgeTable({
  items,
  isLoading = false,
}: {
  items: CollectionOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const del = useDeleteResource();
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  // It holds the ROW: the confirmation names the collection, the request is
  // addressed to its uid.
  const [deleting, setDeleting] = useState<CollectionOut | null>(null);
  const bulk = useBulkMutate({ invalidate: [resourcesKey, knowledgeCollectionsKey] });

  const columns: Column<CollectionOut>[] = [
    {
      key: "name",
      header: t("knowledge.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <ResourceLabel resource={r} />,
    },
    {
      // A CJK header in an unsized column wraps one character per line. The
      // counts are short, so neither column ever needs to wrap at all.
      key: "documents",
      header: t("knowledge.cols.documents"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.document_count}</span>,
    },
    {
      key: "pending",
      header: t("knowledge.cols.pending"),
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <span
          className={r.pending_count > 0 ? "tabular-nums" : "tabular-nums text-muted-foreground"}
        >
          {r.pending_count}
        </span>
      ),
    },
    {
      // The flexible column: it takes the remaining width, which is what stops
      // the fixed ones being squeezed narrow enough to wrap their headers.
      key: "description",
      header: t("knowledge.cols.description"),
      className: "w-full min-w-[16rem]",
      cell: (r) => <span className="text-sm text-muted-foreground">{r.description ?? ""}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <RowDeleteButton
          ariaLabel={`${t("common.delete")}: ${displayName(r)}`}
          onDelete={() => setDeleting(r)}
        />
      ),
    },
  ];

  return (
    <>
      <DataTable
        rows={items}
        isLoading={isLoading}
        columns={columns}
        rowKey={(r) => r.uid}
        onRowClick={(r) => navigate(`/knowledge/${encodeURIComponent(r.uid)}`)}
        search={{
          accessor: (r) => `${searchableName(r)} ${r.description ?? ""}`,
          placeholder: t("knowledge.searchPlaceholder"),
        }}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${displayName(r)}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <BulkDeleteButton
              title={t("knowledge.delete.title")}
              description={t("knowledge.delete.bulkDescription", {
                count: selectedRows.length,
              })}
              pending={bulk.isPending}
              onConfirm={async () => {
                await bulk.run(selectedRows, (r) => resourcesApi.remove(r.uid));
                clear();
              }}
            />
          ),
        }}
        // Rows exist, so an empty table here means the search matched
        // nothing — the "no collections yet" welcome is the page's, not ours.
        emptyMessage={t("knowledge.noMatches")}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t("knowledge.delete.title")}
        description={t("knowledge.delete.description", {
          name: deleting ? displayName(deleting) : "",
        })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        variant="destructive"
        pending={del.isPending}
        onConfirm={() => {
          // Close only on success; the hook toasts a failure and the dialog
          // stays up so the reader can retry or cancel.
          if (deleting === null) return;
          del.mutate(
            { kind: KIND, uid: deleting.uid },
            {
              onSuccess: () => {
                setDeleting(null);
                void qc.invalidateQueries({ queryKey: knowledgeCollectionsKey });
              },
            },
          );
        }}
      />
    </>
  );
}
