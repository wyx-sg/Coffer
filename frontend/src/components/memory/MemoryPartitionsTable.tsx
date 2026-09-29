// frontend/src/components/memory/MemoryPartitionsTable.tsx
//
// The partitions list: one row per repository partition plus `global`, each one
// a `memory` Resource (spec memory "Partition by
// repository plus global"). A row carries what a partition
// has — its name, the repository it is keyed on, how many notes it holds — and
// nothing else.
//
// There is NO status or reach column and no bulk bar. The `memory` kind
// declares itself non-toggleable: every partition is served to every agent
// (spec memory "Serve every partition to every agent"), because aggregating
// the agents' memory into one place exists so that each can read what the
// others learned. A control there would offer a choice with nothing behind it
// (spec web-ui "Show reach as a labelled button on every list and detail
// page"). With no bulk action to apply, the table carries no selection either.
//
// A partition is keyed on a REPOSITORY, not on a working directory: a worktree
// and a second clone resolve to one partition (see "Identify a partition by its
// repository"), so the column names the
// repository rather than the folder some session happened to run in. When that
// repository is no longer on disk the row says so instead of hiding: such a
// partition is delivered to nobody, and deleting it is the developer's call and
// nobody else's (see "Report unresolvable partitions").
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { searchableName } from "@/lib/resourceTitle";
import { ResourceLabel } from "@/components/resource/ResourceLabel";

export function MemoryPartitionsTable({
  rows,
  isLoading = false,
}: {
  rows: PartitionOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const columns: Column<PartitionOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      cell: (r) => <ResourceLabel resource={r} />,
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
  ];

  return (
    <DataTable
      rows={rows}
      isLoading={isLoading}
      columns={columns}
      rowKey={(r) => r.uid}
      onRowClick={(r) => navigate(`/memory/${encodeURIComponent(r.uid)}`)}
      search={{
        accessor: (r) => `${searchableName(r)} ${r.repository_path}`,
        placeholder: t("memory.searchPlaceholder"),
      }}
      emptyMessage={t("memory.empty")}
    />
  );
}
