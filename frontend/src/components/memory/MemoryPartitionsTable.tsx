// frontend/src/components/memory/MemoryPartitionsTable.tsx
//
// The partitions list (spec memory "Present a partition as its memories"): one
// row per repository partition plus `global`, each a `memory` Resource. A row
// carries its name, the repository path it is keyed on ("Every project" for
// global) and how many memories it holds.
//
// There is NO status or reach column, no selection and no search. The `memory`
// kind is not toggleable: every partition is served to every agent (spec
// memory "Serve every partition to every agent"), so a control there would
// offer a choice with nothing behind it (spec web-ui "Show reach as a labelled
// button on every list and detail page").
//
// A partition whose repository is no longer on disk says so instead of hiding,
// and only that row offers Delete: any other partition would come back on the
// next Update memory (spec memory "Report unresolvable partitions"). The
// confirmation is hoisted to table level so closing it cannot click through
// to the row.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { DeletePartitionDialog } from "@/components/memory/DeletePartitionDialog";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { ResourceLabel } from "@/components/resource/ResourceLabel";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { displayName } from "@/lib/resourceTitle";

interface Props {
  rows: PartitionOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}

export function MemoryPartitionsTable({ rows, isLoading = false }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState<PartitionOut | null>(null);

  const columns: Column<PartitionOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      className: "whitespace-nowrap",
      cell: (r) => <ResourceLabel resource={r} />,
    },
    {
      key: "path",
      header: t("memory.cols.path"),
      className: "w-full min-w-[16rem]",
      cell: (r) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="line-clamp-1 text-sm text-text-muted">
            {r.repository_path ? abbreviateHomePath(r.repository_path) : t("memory.cols.global")}
          </span>
          {r.unresolvable ? <UnresolvableBadge /> : null}
        </span>
      ),
    },
    {
      key: "memories",
      header: t("memory.cols.memories"),
      className: "whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.note_count}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) =>
        r.unresolvable ? (
          <RowDeleteButton
            ariaLabel={`${t("common.delete")}: ${displayName(r)}`}
            onDelete={() => setDeleting(r)}
          />
        ) : null,
    },
  ];

  return (
    <>
      <DataTable
        rows={rows}
        isLoading={isLoading}
        columns={columns}
        rowKey={(r) => r.uid}
        onRowClick={(r) => navigate(`/memory/${encodeURIComponent(r.uid)}`)}
        // Never shown in practice: with no partitions the page shows the
        // first-run state instead of the table.
        emptyMessage={t("memory.welcome.title")}
      />
      <DeletePartitionDialog partition={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}
