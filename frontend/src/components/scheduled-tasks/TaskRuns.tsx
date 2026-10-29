// src/components/scheduled-tasks/TaskRuns.tsx — an open task's History: every run, newest first, with how it ended and why.
//
// A row is when the run started (and when it was due, for a late or skipped
// one), the outcome pill, and the reason the daemon gave.
import { useTranslation } from "react-i18next";

import { RelativeTime } from "@/components/RelativeTime";
import { Section } from "@/components/Section";
import { StatusPill } from "@/components/status/StatusPill";
import { useScheduledTaskRuns } from "@/lib/hooks/useScheduledTasks";
import { OUTCOME_TONE } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";

export function TaskRuns({ uid }: { uid: string }) {
  const { t, i18n } = useTranslation();
  const { data, isPending } = useScheduledTaskRuns(uid);
  const runs = data ?? [];
  return (
    <Section title={t("scheduledTasks.runs.title")} help={t("scheduledTasks.runs.help")}>
      {isPending ? null : runs.length === 0 ? (
        <p className="text-xs text-text-muted">{t("scheduledTasks.runs.none")}</p>
      ) : (
        <ul className="divide-y divide-border-subtle rounded-lg border border-border-subtle">
          {runs.map((run) => (
            <li key={run.run_id} className="flex items-start gap-3 px-3 py-2 text-xs">
              <span className="w-24 shrink-0 pt-0.5 text-text-muted">
                <RelativeTime iso={run.started_at} />
              </span>
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="flex flex-wrap items-center gap-2">
                  <StatusPill tone={OUTCOME_TONE[run.outcome]}>
                    {t(`scheduledTasks.outcome.${run.outcome}`)}
                  </StatusPill>
                  {run.trigger === "manual" ? (
                    <span className="text-text-muted">{t("scheduledTasks.runs.byHand")}</span>
                  ) : null}
                  {run.catch_up ? (
                    <span className="text-text-muted">
                      {t("scheduledTasks.runs.late", {
                        due: formatMoment(run.due_at, i18n.language, t),
                      })}
                    </span>
                  ) : null}
                </span>
                {run.reason ? (
                  <span className="block break-words text-text-muted">{run.reason}</span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
