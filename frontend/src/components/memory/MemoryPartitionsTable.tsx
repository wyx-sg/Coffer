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
// Status is a grey dot plus its words ("Distilled 2 h ago"); a partition whose
// repository is no longer on disk says so in warning colour instead of hiding,
// and only that row offers Delete…: any other partition would come back on the
// next Update memory (spec memory "Report unresolvable partitions"). The
// confirmation is hoisted to table level so closing it cannot click through
// to the row.
import { useState } from "react";
import { AgentSources, distilState, sampleLine } from "@/components/memory/partitionFacts";
import { useUpkeepRunsOf } from "@/lib/hooks/useUpkeep";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";
import { DeletePartitionDialog } from "@/components/memory/DeletePartitionDialog";
import { UnresolvableBadge } from "@/components/memory/UnresolvableBadge";
import { ResourceLabel } from "@/components/resource/ResourceLabel";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { displayName } from "@/lib/resourceTitle";

interface Props {
  rows: PartitionOut[];
  /** Skeleton rows while the list resolves — the page keeps its header up. */
  isLoading?: boolean;
}

export function MemoryPartitionsTable({ rows, isLoading = false }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState<PartitionOut | null>(null);
  const runs = useUpkeepRunsOf("memory");
  const running = (uid: string) => runs.some((r) => r.name === uid);
  // "All agents" means every agent that contributed to any partition.
  const everyone = [...new Set(rows.flatMap((r) => r.sources))];

  const columns: Column<PartitionOut>[] = [
    {
      key: "name",
      header: t("memory.cols.name"),
      className: "w-[20%]",
      cell: (r) => <ResourceLabel resource={r} truncate />,
    },
    {
      key: "path",
      header: t("memory.cols.path"),
      className: "w-[22%]",
      cell: (r) =>
        r.repository_path ? (
          <TruncatedPath
            text={abbreviateHomePath(r.repository_path)}
            className="font-mono text-2xs text-text-muted"
          />
        ) : (
          <span className="text-xs text-text-muted">{t("memory.cols.global")}</span>
        ),
    },
    {
      key: "sample",
      header: t("memory.cols.sample"),
      cell: (r) => (
        <TruncatedText
          text={sampleLine(t, r)}
          className={r.sample ? "text-sm text-text" : "text-sm text-text-subtle"}
        />
      ),
    },
    {
      key: "memories",
      header: t("memory.cols.memories"),
      className: "w-[96px] whitespace-nowrap text-right",
      cell: (r) => <span className="tabular-nums">{r.note_count}</span>,
    },
    {
      key: "sources",
      header: t("memory.cols.sources"),
      className: "w-[140px] whitespace-nowrap",
      cell: (r) => <AgentSources agents={r.sources} everyone={everyone} />,
    },
    {
      key: "distil",
      header: t("memory.cols.distil"),
      className: "w-[170px] whitespace-nowrap",
      // Healthy states are grey; only a missing repository is coloured.
      cell: (r) =>
        r.unresolvable ? (
          <UnresolvableBadge />
        ) : (
          <StatusWord tone="off">{distilState(t, i18n.language, r, running(r.uid))}</StatusWord>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "w-[110px] whitespace-nowrap text-right",
      // Only a partition whose repository is gone can be deleted.
      cell: (r) =>
        r.unresolvable ? (
          <TableActionButton
            icon={Trash2}
            label={`${t("common.delete")}…`}
            destructive
            aria-label={`${t("common.delete")}: ${displayName(r)}`}
            onClick={() => setDeleting(r)}
          />
        ) : null,
    },
  ];

  return (
    <>
      <DataTable
        fixed
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
