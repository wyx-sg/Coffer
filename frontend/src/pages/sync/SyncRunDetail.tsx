// frontend/src/pages/sync/SyncRunDetail.tsx
//
// One round opened up: everything its row could not carry — the snapshot it
// took before checking anything out, the commits it pulled and from whom, the
// files it changed here and the files it pushed, and git's own words when it
// could not finish.
import { useTranslation } from "react-i18next";

import type { SyncRound } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { SyncRoundPathList } from "./SyncRoundPathList";
import { changeLine } from "./syncRoundStatus";

function seconds(from: string, to: string): number {
  const ms = new Date(to).getTime() - new Date(from).getTime();
  return Number.isFinite(ms) ? Math.max(0, Math.round(ms / 100) / 10) : 0;
}

export function SyncRunDetail({ run }: { run: SyncRound }) {
  const { t } = useTranslation();
  const said =
    run.snapshot ||
    run.pulled.length > 0 ||
    run.applied.length > 0 ||
    run.pushed.length > 0 ||
    run.detail;

  return (
    <div className="space-y-3 px-4 py-3">
      <p className="text-xs text-muted-foreground">
        {t("sync.runs.ran", {
          from: formatDateTime(run.started_at),
          seconds: seconds(run.started_at, run.finished_at),
          trigger: run.trigger,
        })}
      </p>
      {run.snapshot ? (
        <p className="text-xs" data-testid="sync-run-snapshot">
          {t("sync.runs.snapshot", { name: run.snapshot })}
        </p>
      ) : null}
      <SyncRoundPathList
        titleKey="sync.runs.pulledCommits"
        items={run.pulled.map((c) =>
          t("sync.runs.pulledCommit", {
            sha: c.version.slice(0, 7),
            machine: c.machine ?? t("sync.runs.unknownMachine"),
            files: c.files,
            when: formatDateTime(c.time),
          }),
        )}
        testId="sync-run-pulled"
      />
      <SyncRoundPathList
        titleKey="sync.runs.applied"
        items={run.applied.map(changeLine)}
        testId="sync-run-applied"
      />
      <SyncRoundPathList
        titleKey="sync.runs.pushed"
        items={run.pushed.map(changeLine)}
        testId="sync-run-pushed"
      />
      {run.with_machines.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("sync.runs.withMachines", { names: run.with_machines.join(", ") })}
        </p>
      ) : null}
      {/* The daemon scrubbed any push token out of this before storing it. */}
      {run.detail ? (
        <p className="text-xs text-destructive" role="alert">
          {run.path ? `${run.path}: ` : ""}
          {run.detail}
        </p>
      ) : null}
      {!said ? (
        <p className="text-sm text-muted-foreground">{t("sync.runs.nothingFurther")}</p>
      ) : null}
    </div>
  );
}
