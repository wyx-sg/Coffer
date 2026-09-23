// frontend/src/pages/sync/SyncRunDetail.tsx
//
// One round opened up: everything its row could not carry — the paths it moved
// in each direction, the conflicts, what an agent resolved, what failed, and
// the credential refs it could not touch.
//
// Split out of SyncRunsTab so that file stays a tab (query, folding, filters,
// states) rather than also being a renderer — the same seam syncRunColumns.tsx
// takes for the row itself.
import { useTranslation } from "react-i18next";

import type { RunRecord } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { SyncJoinReport } from "./SyncJoinReport";
import { SyncRoundPathList } from "./SyncRoundPathList";

/** One round opened up: everything the row could not carry. */
export function SyncRunDetail({ run }: { run: RunRecord }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3 px-4 py-3">
      <p className="text-xs text-muted-foreground">
        {t("sync.history.ran", {
          from: formatDateTime(run.started_at),
          to: formatDateTime(run.finished_at),
        })}
      </p>
      {/* On an awaiting_join round the kind is what was DETECTED, not done. */}
      {run.join && run.status !== "awaiting_join" ? (
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
        titleKey="sync.round.notApplicable"
        hintKey="sync.round.notApplicableHint"
        items={run.not_applicable}
        testId="sync-run-not-applicable"
      />
      {run.status === "awaiting_join" ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{t("sync.round.awaitingJoin")}</p>
          {run.join_report ? (
            <>
              <p className="text-sm">{t(`sync.join.detected.${run.join_report.case ?? "new"}`)}</p>
              <SyncJoinReport report={run.join_report} />
            </>
          ) : null}
        </div>
      ) : null}
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
      run.not_applicable.length === 0 &&
      run.status !== "awaiting_join" &&
      run.locked_refs.length === 0 &&
      !run.error ? (
        <p className="text-sm text-muted-foreground">{t("sync.history.nothingFurther")}</p>
      ) : null}
    </div>
  );
}
