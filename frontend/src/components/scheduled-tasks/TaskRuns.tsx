// src/components/scheduled-tasks/TaskRuns.tsx — an open task's History tab: every run as a table, newest first.
//
// A row is when the run started, how it ended, how it was started (on
// schedule, late, or by hand), how long it took, the reason the daemon gave,
// and the conversation it used. The table searches the reasons and the
// conversations' titles and filters by outcome and by how a run started. A
// conversation's title links to the Conversations page, which selects it in
// its list without opening it, to read the run or carry it on (spec scheduled-tasks
// "Keep every scheduled run in the task's history").
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { StatusPill } from "@/components/status/StatusPill";
import type { RunOutcome, ScheduledRun } from "@/lib/api/scheduledTasks";
import { formatDuration } from "@/lib/format/duration";
import { useScheduledTaskRuns } from "@/lib/hooks/useScheduledTasks";
import { OUTCOME_TONE, RUNS_SHOWN } from "@/lib/scheduledTasks/format";
import { formatExact, formatMoment } from "@/lib/time";

const OUTCOMES: readonly RunOutcome[] = ["running", "done", "skipped", "failed", "stopped"];

/** How a run started: by hand, late for its slot, or on time. */
function startedBy(run: ScheduledRun): "manual" | "late" | "schedule" {
  if (run.trigger === "manual") return "manual";
  return run.catch_up ? "late" : "schedule";
}

export function TaskRuns({ uid }: { uid: string }) {
  const { t, i18n } = useTranslation();
  const { data, isPending } = useScheduledTaskRuns(uid);
  const runs = data ?? [];

  const columns: Column<ScheduledRun>[] = [
    {
      key: "started",
      header: t("scheduledTasks.runs.started"),
      className: "w-[18%]",
      sortable: true,
      sortValue: (r) => r.started_at,
      // The moment itself ("today at 17:42"), not "6 min ago": runs are read by when they ran.
      cell: (r) => (
        <time
          dateTime={r.started_at}
          title={formatExact(r.started_at, i18n.language)}
          className="text-text-muted"
        >
          {formatMoment(r.started_at, i18n.language, t)}
        </time>
      ),
    },
    {
      key: "outcome",
      header: t("scheduledTasks.runs.outcome"),
      className: "w-[14%]",
      cell: (r) => (
        <StatusPill tone={OUTCOME_TONE[r.outcome]}>
          {t(`scheduledTasks.outcome.${r.outcome}`)}
        </StatusPill>
      ),
    },
    {
      key: "trigger",
      header: t("scheduledTasks.runs.trigger"),
      className: "w-[16%]",
      cell: (r) => {
        const by = startedBy(r);
        return (
          <span
            className="text-text-muted"
            title={by === "late" ? formatMoment(r.due_at, i18n.language, t) : undefined}
          >
            {t(`scheduledTasks.runs.by.${by}`)}
          </span>
        );
      },
    },
    {
      key: "duration",
      header: t("scheduledTasks.runs.duration"),
      className: "w-[10%]",
      sortable: true,
      sortValue: (r) =>
        r.finished_at ? Date.parse(r.finished_at) - Date.parse(r.started_at) : null,
      cell: (r) => (
        <span className="text-text-muted tabular-nums">
          {r.finished_at
            ? formatDuration(Date.parse(r.finished_at) - Date.parse(r.started_at))
            : "—"}
        </span>
      ),
    },
    {
      key: "conversation",
      header: t("scheduledTasks.runs.conversationColumn"),
      cell: (r) =>
        r.conversation ? (
          <Link
            to={`/conversations?open=${encodeURIComponent(r.conversation.conversation_id)}`}
            className="block truncate text-accent-text hover:underline"
          >
            {r.conversation.title}
          </Link>
        ) : r.conversation_id ? (
          <span className="text-text-subtle">{t("scheduledTasks.runs.conversationGone")}</span>
        ) : (
          <span className="block break-words text-text-muted">{r.reason}</span>
        ),
    },
  ];

  const filters: FilterDef<ScheduledRun>[] = [
    {
      key: "outcome",
      label: t("scheduledTasks.runs.outcome"),
      options: OUTCOMES.map((o) => ({ value: o, label: t(`scheduledTasks.outcome.${o}`) })),
      accessor: (r) => r.outcome,
    },
    {
      key: "trigger",
      label: t("scheduledTasks.runs.trigger"),
      options: (["schedule", "late", "manual"] as const).map((v) => ({
        value: v,
        label: t(`scheduledTasks.runs.by.${v}`),
      })),
      accessor: startedBy,
    },
  ];

  return (
    <div className="flex flex-col gap-2">
      <DataTable
        rows={runs}
        columns={columns}
        rowKey={(r) => r.run_id}
        fixed
        isLoading={isPending}
        search={{
          placeholder: t("scheduledTasks.runs.search"),
          accessor: (r) => `${r.reason} ${r.conversation?.title ?? ""}`,
        }}
        filters={filters}
        rowFooter={(r) =>
          r.reason && r.conversation_id ? (
            <span className="text-xs text-text-muted">{r.reason}</span>
          ) : null
        }
        emptyMessage={t("scheduledTasks.runs.none")}
      />
      {runs.length >= RUNS_SHOWN ? (
        <p className="text-xs text-text-subtle">
          {t("scheduledTasks.runs.latestOnly", { count: RUNS_SHOWN })}
        </p>
      ) : null}
    </div>
  );
}
