// frontend/src/components/memory/MemoryPartitionsTable.tsx
//
// The partitions list: one row per repository partition plus `global`, each one
// a `memory` Resource (spec memory FR-010). A row carries what a partition
// has — its name, the repository it is keyed on, how many notes it holds —
// plus the reach control every scoped Resource gets (ScopeControl), exactly as
// the mcp-servers and skills lists render it per row, and a bulk bar applying
// that same reach choice to the whole selection.
//
// A partition is keyed on a REPOSITORY, not on a working directory: a worktree
// and a second clone resolve to one partition (FR-014), so the column names the
// repository rather than the folder some session happened to run in. When that
// repository is no longer on disk the row says so instead of hiding: such a
// partition is delivered to nobody, and deleting it is the developer's call and
// nobody else's (FR-016).
//
// `enabled`/`scope` do not live on the dedicated partitions endpoint (it only
// carries what is read off disk: name, repository path and key, note count,
// whether it still resolves) — they are generic Resource fields, so the caller
// merges in `GET /resources?kind=memory` before rendering, mirroring how the
// mcp-servers table already carries `scope` on its own row payload rather than
// paying one GET per row.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { memoryKey } from "@/lib/api/queryKeys";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import type { Scope } from "@/lib/hooks/useScope";
import { reachFilter } from "@/lib/reachFilter";

export interface MemoryPartitionRow extends PartitionOut {
  enabled: boolean;
  scope: Scope | null;
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
      key: "reach",
      header: t("resources.cols.reach"),
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
          <ScopeControl kind="memory" name={r.name} enabled={r.enabled} scope={r.scope} />
        </div>
      ),
    },
  ];

  return (
    <DataTable
      rows={rows}
      isLoading={isLoading}
      columns={columns}
      rowKey={(r) => r.name}
      onRowClick={(r) => navigate(`/memory/${encodeURIComponent(r.name)}`)}
      search={{
        accessor: (r) => `${r.name} ${r.repository_path}`,
        placeholder: t("memory.searchPlaceholder"),
      }}
      filters={[reachFilter(t, (r: MemoryPartitionRow) => r)]}
      // No bulk delete: a partition is aggregated from the agents' own
      // memories, never user-created, so there is nothing here to remove — the
      // selection bar carries reach alone.
      selection={{
        ariaSelectAll: t("common.bulk.selectAll"),
        ariaSelectRow: (r) => `${t("common.bulk.selectRow")}: ${r.name}`,
        bulkLabel: (count) => t("common.bulk.selected", { count }),
        clearLabel: t("common.clear"),
        renderBulkActions: ({ selectedRows, clear }) => (
          <BulkReachActions
            rows={selectedRows.map((r) => ({ kind: "memory", name: r.name }))}
            invalidate={[memoryKey]}
            onDone={clear}
          />
        ),
      }}
      emptyMessage={t("memory.empty")}
    />
  );
}
