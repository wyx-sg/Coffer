// frontend/src/pages/sync/SyncHistoryTab.tsx — Sync → History.
//
// Every converge round this machine has run, newest first (spec vault-sync
// `## The converge round`). This replaced the single "Last round" card on
// Status: one round's prose could say what just happened but never what has
// been happening, and the questions a user actually brings to this page —
// has it been running, when did it stop, which round published those 300
// documents — are all questions about the sequence.
//
// The shared DataTable, so search, the status filter and paging come for free
// and this does not become a bespoke table. The whole window arrives in one
// request and is filtered in the browser, exactly as the Activity page's tabs
// do, because 500 rounds is a small payload and a server round-trip per
// keystroke is not worth it.
//
// Rounds that changed nothing are listed like any other. They are the majority
// and they are what makes a GAP visible: without them, a vault that stopped
// converging on Tuesday looks the same as one that has had nothing to do.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type FilterDef } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import { useSyncRuns } from "@/lib/hooks/useSync";
import type { RunRecord } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";
import { rollbackTargetId, runSearchHaystack, statusLabel, syncRunColumns } from "./syncRunColumns";

/** The statuses a round can end in — the filter's options, in severity order. */
const STATUSES = [
  "ok",
  "no_change",
  "conflict",
  "awaiting_confirmation",
  "push_failed",
  "failed",
  "disabled",
] as const;

interface Props {
  /** False while another tab is in front: no request, no discarded response. */
  enabled: boolean;
}

/** One round opened up: everything the row could not carry. */
function RunDetail({ run }: { run: RunRecord }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3 px-4 py-3">
      <p className="text-xs text-muted-foreground">
        {t("sync.history.ran", {
          from: formatDateTime(run.started_at),
          to: formatDateTime(run.finished_at),
        })}
      </p>
      {run.join ? (
        <p className="text-sm text-muted-foreground">{t(`sync.round.join.${run.join}`)}</p>
      ) : null}

      {/* What the round actually moved. The row above carries the tally; this
          is the question the tally raises, and the paths were in the stored
          payload all along — the detail used to skip straight to the faults
          and tell a round that changed two documents there was nothing
          further to report. */}
      <SyncRoundPathList
        titleKey="sync.round.applied"
        hintKey="sync.round.appliedHint"
        items={run.applied.changes.map((c) => t(`sync.round.change.${c.status}`, { path: c.path }))}
        testId="sync-run-applied"
      />
      <SyncRoundPathList
        titleKey="sync.round.published"
        hintKey="sync.round.publishedHint"
        items={run.published.changes.map((c) =>
          t(`sync.round.change.${c.status}`, { path: c.path }),
        )}
        testId="sync-run-published"
      />

      <SyncRoundPathList
        titleKey="sync.conflict.paths"
        items={run.conflicts}
        tone="err"
        testId="sync-run-conflicts"
      />
      <SyncRoundPathList
        titleKey="sync.round.agentResolved"
        hintKey="sync.round.agentResolvedHint"
        items={run.agent_resolved}
        testId="sync-run-agent-resolved"
      />
      <SyncRoundPathList
        titleKey="sync.round.failures"
        items={run.failures.map((f) => t("sync.round.failure", { path: f.path, reason: f.reason }))}
        tone="err"
        testId="sync-run-failures"
      />
      <SyncRoundPathList
        titleKey="sync.round.lockedRefs"
        hintKey="sync.round.lockedRefsHint"
        items={run.locked_refs}
        tone="warn"
        testId="sync-run-locked-refs"
      />

      {/* The daemon scrubbed any push token out of this before storing it;
          nothing here needs to redact, and nothing here should start. */}
      {run.error ? (
        <p className="text-xs text-destructive" role="alert">
          {run.error}
        </p>
      ) : null}

      {!run.join &&
      run.applied.changes.length === 0 &&
      run.published.changes.length === 0 &&
      run.conflicts.length === 0 &&
      run.agent_resolved.length === 0 &&
      run.failures.length === 0 &&
      run.locked_refs.length === 0 &&
      !run.error ? (
        <p className="text-sm text-muted-foreground">{t("sync.history.nothingFurther")}</p>
      ) : null}
    </div>
  );
}

export function SyncHistoryTab({ enabled }: Props) {
  const { t } = useTranslation();
  // isLoading, not isPending: a disabled query stays "pending" forever, which
  // would leave a tab that has never been opened stuck on the loading card the
  // moment it is.
  const { data, isLoading, error } = useSyncRuns(enabled);
  const runs = useMemo(() => data?.runs ?? [], [data]);
  // Which row may offer "Undo this round": `POST /sync/rollback` names no
  // round, it reverses the newest pre-apply snapshot, so exactly one row can
  // honestly carry the action. Computed over the WHOLE history rather than the
  // visible page — a filter that hides the newest round must not promote the
  // one under it into a target it is not.
  const rollbackTarget = useMemo(() => rollbackTargetId(runs), [runs]);

  const filters: FilterDef<RunRecord>[] = [
    {
      key: "status",
      label: t("sync.history.filter.outcome"),
      allLabel: t("resources.status.all"),
      accessor: (run) => run.status,
      options: STATUSES.map((s) => ({ value: s, label: statusLabel(t, s) })),
    },
  ];

  if (isLoading) {
    return (
      <Card className="paper-card">
        <CardContent className="py-10 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  // An error renders inside this tab — a daemon too old to serve /sync/runs
  // 404s, and that must not blank the two tabs it does still serve.
  if (error) {
    return (
      <Card className="paper-card border-destructive/40">
        <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("sync.history.description")}</p>
      {/* No re-sort: the daemon returns the rounds newest-first and DataTable
          preserves the order it is handed. */}
      <DataTable
        rows={runs}
        columns={syncRunColumns(t, rollbackTarget)}
        rowKey={(run) => String(run.id)}
        search={{
          accessor: (run) => runSearchHaystack(t, run),
          placeholder: t("sync.history.searchPlaceholder"),
        }}
        filters={filters}
        getRowDetail={(run) => <RunDetail run={run} />}
        emptyMessage={t("sync.history.empty")}
      />
    </div>
  );
}
