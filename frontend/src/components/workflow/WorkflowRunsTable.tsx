// frontend/src/components/workflow/WorkflowRunsTable.tsx
// The run list: what is being delivered, from which template, where it got to,
// when it last moved, and which machine is advancing it.
//
// "Where it is" is one column reading `stage → node`, not two: a run's
// position is one fact, and splitting it across two headers made a reader
// reassemble it on every row.
//
// The owner column is not decoration. A run belongs to one machine (FR-012)
// and only that machine's daemon advances it; everywhere else the run is
// visible and its commands refused. A row for a foreign run still navigates —
// reading a run is never gated — and it is the run's own page that disables
// its actions and says which machine to go to.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";
import { useMachineLabel } from "@/lib/hooks/useWorkflowRuns";
import type { Run } from "@/lib/api/workflow";
import { RunStatusBadge } from "./WorkflowStatusBadge";

interface Props {
  runs: Run[];
  isLoading?: boolean;
  onDelete: (run: Run) => void;
}

export function WorkflowRunsTable({ runs, isLoading = false, onDelete }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const machineLabel = useMachineLabel();

  const columns: Column<Run>[] = [
    {
      key: "title",
      header: t("workflow.cols.title"),
      className: "w-full min-w-[14rem]",
      cell: (r) => <span className="font-medium">{r.title}</span>,
    },
    {
      key: "template",
      header: t("workflow.cols.template"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="text-muted-foreground">{r.template_ref}</span>,
    },
    {
      key: "status",
      header: t("workflow.cols.status"),
      className: "whitespace-nowrap",
      cell: (r) => <RunStatusBadge status={r.status} />,
    },
    {
      key: "position",
      header: t("workflow.cols.position"),
      className: "whitespace-nowrap",
      cell: (r) =>
        r.current_stage_key ? (
          <span className="text-muted-foreground">
            {r.current_stage_key}
            {r.current_node_key ? ` → ${r.current_node_key}` : ""}
          </span>
        ) : (
          <span className="text-muted-foreground">{t("common.emptyValue")}</span>
        ),
    },
    {
      key: "moved",
      header: t("workflow.cols.lastMoved"),
      className: "whitespace-nowrap",
      cell: (r) => (
        <span className="text-muted-foreground">
          {formatDateTime(r.updated_at ?? r.created_at)}
        </span>
      ),
    },
    {
      key: "owner",
      header: t("workflow.cols.owner"),
      className: "whitespace-nowrap",
      cell: (r) =>
        r.owned_here ? (
          <Badge variant="outline">{t("workflow.owner.thisMachine")}</Badge>
        ) : (
          <Badge variant="secondary">{machineLabel(r.machine_id)}</Badge>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      cell: (r) => (
        <RowDeleteButton
          ariaLabel={`${t("workflow.deleteTitle")}: ${r.title}`}
          onDelete={() => onDelete(r)}
        />
      ),
    },
  ];

  return (
    <DataTable
      rows={runs}
      isLoading={isLoading}
      columns={columns}
      rowKey={(r) => r.id}
      search={{
        accessor: (r) => `${r.title} ${r.template_ref}`,
        placeholder: t("workflow.searchPlaceholder"),
      }}
      filters={[
        {
          key: "status",
          label: t("workflow.cols.status"),
          allLabel: t("workflow.filters.allStatuses"),
          options: (["draft", "running", "paused", "completed", "aborted", "failed"] as const).map(
            (s) => ({ value: s, label: t(`workflow.runStatus.${s}`) }),
          ),
          accessor: (r) => r.status,
        },
      ]}
      onRowClick={(r) => navigate(`/runs/${r.id}`)}
      emptyMessage={t("workflow.noMatches")}
    />
  );
}
