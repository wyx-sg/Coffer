// frontend/src/components/knowledge/KnowledgeTable.tsx
// The collections list, rendered via the shared DataTable. A collection is a
// top-level folder under the knowledge root and one `knowledge` Resource, so a
// row carries what a folder has — its name, what its README says it is for, and
// the size of each of its two lanes — plus the status control every Resource
// gets, in the shape this kind's Resource actually has.
//
// A collection carries NO PER-AGENT REACH. The `knowledge` kind declares no
// scope (the backend answers `supports_scope: false` and refuses a scope
// write), because every enabled collection is served to every agent: an agent
// reads the files at the paths its delivered skill carries, and that skill
// names the collections — there is no per-agent cut of the knowledge root to
// make. So `ScopeControl` and the bulk bar are both told `supportsScope={false}`
// and collapse to the two choices this kind has.
//
// The column survives that because `enabled` is a REAL gate, not a label: a
// disabled collection appears in no agent's delivered skill at all. Only the
// header changes — it says "Status", since enabled/disabled is the whole of
// what it reports.
//
// The lanes are counted APART because they answer different questions: how much
// the person has contributed, and how much of it an agent can read today. A
// collection with sources and no topics is one curation has not reached yet,
// which a single total would hide (spec knowledge FR-001).
//
// `enabled` is a generic Resource field and is NOT on /knowledge/collections
// (which reads the folders off disk), so it is merged in from
// `GET /resources?kind=knowledge` via useKindReach: one extra request for the
// table, never one per row.
//
// Deleting goes through the kind-agnostic resource route, which cascades the
// directory — collection lifecycle is a Resource concern, not a knowledge one.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { DataTable, type Column } from "@/components/DataTable";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { resourcesApi } from "@/lib/api/resources";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { useKindReach } from "@/lib/hooks/useResources";
import { knowledgeCollectionsKey, resourcesKey } from "@/lib/api/queryKeys";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";
import { reachFilter } from "@/lib/reachFilter";

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
  const reach = useKindReach(KIND);
  // Styled confirmation dialog (no native window.confirm). `null` = closed.
  const [deletingName, setDeletingName] = useState<string | null>(null);
  const bulk = useBulkMutate({ invalidate: [resourcesKey, knowledgeCollectionsKey] });

  // `scope` is deliberately not read back out of the merge: this kind declares
  // none, so `enabled` is the whole of a row's status and anything still stored
  // under a collection's name is not this table's answer to anything.
  const reachOf = (r: CollectionOut) => ({
    enabled: reach.get(r.name)?.enabled ?? true,
    scope: null,
  });

  const columns: Column<CollectionOut>[] = [
    {
      key: "name",
      header: t("knowledge.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      // A CJK header in an unsized column wraps one character per line. The
      // counts are short, so neither column ever needs to wrap at all.
      key: "sources",
      header: t("knowledge.cols.sources"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.source_count}</span>,
    },
    {
      key: "topics",
      header: t("knowledge.cols.topics"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.topic_count}</span>,
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
      key: "status",
      // Not "Reach": with no scope to narrow, the control reports one thing.
      header: t("resources.cols.status"),
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
          <ScopeControl kind={KIND} name={r.name} supportsScope={false} {...reachOf(r)} />
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <RowDeleteButton
          ariaLabel={`${t("common.delete")}: ${r.name}`}
          onDelete={() => setDeletingName(r.name)}
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
        rowKey={(r) => r.name}
        onRowClick={(r) => navigate(`/knowledge/${encodeURIComponent(r.name)}`)}
        search={{
          accessor: (r) => `${r.name} ${r.description ?? ""}`,
          placeholder: t("knowledge.searchPlaceholder"),
        }}
        filters={[reachFilter(t, reachOf, false)]}
        selection={{
          ariaSelectAll: t("common.bulk.selectAll"),
          ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
          bulkLabel: (count) => t("common.bulk.selected", { count }),
          clearLabel: t("common.clear"),
          renderBulkActions: ({ selectedRows, clear }) => (
            <>
              <BulkReachActions
                rows={selectedRows.map((r) => ({ kind: KIND, name: r.name }))}
                // Same two choices as the rows: enable or disable the lot, and
                // no scope write the server would refuse anyway.
                supportsScope={false}
                invalidate={[knowledgeCollectionsKey]}
                onDone={clear}
              />
              <BulkDeleteButton
                title={t("knowledge.delete.title")}
                description={t("knowledge.delete.bulkDescription", {
                  count: selectedRows.length,
                })}
                pending={bulk.isPending}
                onConfirm={async () => {
                  await bulk.run(selectedRows, (r) => resourcesApi.remove(KIND, r.name));
                  clear();
                }}
              />
            </>
          ),
        }}
        // Rows exist, so an empty table here means the search/filter matched
        // nothing — the "no collections yet" welcome is the page's, not ours.
        emptyMessage={t("knowledge.noMatches")}
      />
      <ConfirmDialog
        open={deletingName !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingName(null);
        }}
        title={t("knowledge.delete.title")}
        description={t("knowledge.delete.description", { name: deletingName ?? "" })}
        confirmLabel={del.isPending ? t("common.deleting") : t("common.delete")}
        variant="destructive"
        pending={del.isPending}
        onConfirm={() => {
          // Close only on success; the hook toasts a failure and the dialog
          // stays up so the reader can retry or cancel.
          if (deletingName === null) return;
          del.mutate(
            { kind: KIND, name: deletingName },
            {
              onSuccess: () => {
                setDeletingName(null);
                void qc.invalidateQueries({ queryKey: knowledgeCollectionsKey });
              },
            },
          );
        }}
      />
    </>
  );
}
