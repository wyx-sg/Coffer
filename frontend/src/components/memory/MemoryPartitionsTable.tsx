// frontend/src/components/memory/MemoryPartitionsTable.tsx
//
// The partitions list: one row per repository partition plus `global`, each one
// a `memory` Resource (spec memory FR-010). A row carries what a partition
// has — its name, the repository it is keyed on, how many notes it holds —
// plus the status control every Resource gets (ScopeControl), and a bulk bar
// applying that same choice to the whole selection.
//
// A partition carries NO PER-AGENT REACH. The `memory` kind declares no scope
// (the backend answers `supports_scope: false` and refuses a scope write):
// memory is aggregated from every agent's own notes and served back to every
// agent, so cutting a partition per agent would hide from one agent what it
// wrote itself. `ScopeControl` and the bulk bar are therefore both told
// `supportsScope={false}` and collapse to the two choices this kind has.
//
// The column survives that because `enabled` is a REAL gate, not a label: a
// disabled partition is served to nobody. Only the header changes — it says
// "Status", since enabled/disabled is the whole of what it reports.
//
// A partition is keyed on a REPOSITORY, not on a working directory: a worktree
// and a second clone resolve to one partition (FR-014), so the column names the
// repository rather than the folder some session happened to run in. When that
// repository is no longer on disk the row says so instead of hiding: such a
// partition is delivered to nobody, and deleting it is the developer's call and
// nobody else's (FR-016).
//
// `enabled` does not live on the dedicated partitions endpoint (it only
// carries what is read off disk: name, repository path and key, note count,
// whether it still resolves) — it is a generic Resource field, so the caller
// merges in `GET /resources?kind=memory` before rendering, which is also what
// keeps the row control off the per-resource query: one request for the table,
// never one per row.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { memoryKey } from "@/lib/api/queryKeys";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { reachFilter } from "@/lib/reachFilter";

export interface MemoryPartitionRow extends PartitionOut {
  /** The only Resource field this row needs: the kind declares no scope, so
   *  enabled/disabled is the whole of a partition's status. */
  enabled: boolean;
}

export function MemoryPartitionsTable({
  rows,
  isLoading = false,
}: {
  rows: MemoryPartitionRow[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<MemoryPartitionRow>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "repository",
      header: t("memory.cols.repository"),
      className: "w-full min-w-[16rem]",
      cell: (r) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="line-clamp-1 text-sm text-muted-foreground">
            {r.repository_path || t("memory.cols.global")}
          </span>
          {/* Stated on the row, not filtered out of it: the partition is
              delivered to nobody, and only the developer can decide whether
              that is a repository to re-clone or a partition to delete. */}
          {r.unresolvable ? <UnresolvableBadge /> : null}
        </span>
      ),
    },
    {
      key: "notes",
      header: t("memory.cols.notes"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.note_count}</span>,
    },
    {
      key: "status",
      // Not "Reach": with no scope to narrow, the control reports one thing.
      header: t("resources.cols.status"),
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
          {/* `scope={null}` is what keeps the control off the per-resource
              query — it is a supplied value, not a missing one. */}
          <ScopeControl
            kind="memory"
            uid={r.uid}
            enabled={r.enabled}
            scope={null}
            supportsScope={false}
          />
        </div>
      ),
    },
  ];

  return (
    <DataTable
      rows={rows}
      isLoading={isLoading}
      columns={columns}
      rowKey={(r) => r.uid}
      onRowClick={(r) => navigate(`/memory/${encodeURIComponent(r.uid)}`)}
      search={{
        accessor: (r) => `${r.name} ${r.repository_path}`,
        placeholder: t("memory.searchPlaceholder"),
      }}
      filters={[reachFilter(t, (r: MemoryPartitionRow) => ({ ...r, scope: null }), false)]}
      // No bulk delete: a partition is aggregated from the agents' own
      // memories, never user-created, so there is nothing here to remove — the
      // selection bar carries the enable/disable choice alone.
      selection={{
        ariaSelectAll: t("common.bulk.selectAll"),
        ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
        bulkLabel: (count) => t("common.bulk.selected", { count }),
        clearLabel: t("common.clear"),
        renderBulkActions: ({ selectedRows, clear }) => (
          <BulkReachActions
            rows={selectedRows.map((r) => ({ kind: "memory", uid: r.uid }))}
            // Same two choices as the rows: enable or disable the lot, and no
            // scope write the server would refuse anyway.
            supportsScope={false}
            invalidate={[memoryKey]}
            onDone={clear}
          />
        ),
      }}
      emptyMessage={t("memory.empty")}
    />
  );
}
