// src/components/scheduled-tasks/TaskPane.tsx — the open task (board TaskDetail): its header and actions, then What it does and History.
//
// The header is the name with its state pill and one meta line (where it runs ·
// the schedule in words · next run). What it does lists the prompt, how the
// conversation opens, catch-up, and, for a follow-up, who booked it and where
// the chain stands. History is every run.
import { CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Section, SectionStack } from "@/components/Section";
import { StatusPill } from "@/components/status/StatusPill";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { STATE_TONE, scheduleText, taskState } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";
import { TaskActions } from "./TaskActions";
import { TaskRuns } from "./TaskRuns";

interface Props {
  task: ScheduledTask;
  onDeleted: () => void;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 py-1.5 text-xs">
      <dt className="text-text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-text">{children}</dd>
    </div>
  );
}

export function TaskPane({ task, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const state = taskState(task);
  const c = task.config;
  const meta = [
    task.channel_name,
    scheduleText(t, c.schedule, i18n.language),
    task.next_run
      ? t("scheduledTasks.detail.next", { next: formatMoment(task.next_run, i18n.language, t) })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const opens =
    c.session === "continue"
      ? t("scheduledTasks.detail.continues")
      : [c.agent, c.model, c.cwd].filter(Boolean).join(" · ") ||
        t("scheduledTasks.detail.freshDefault");
  return (
    <div className="flex flex-col gap-5">
      <header className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <CalendarClock className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="min-w-0 truncate text-lg font-semibold text-text">{task.name}</h2>
            <StatusPill tone={STATE_TONE[state]}>{t(`scheduledTasks.state.${state}`)}</StatusPill>
          </div>
          <p className="min-w-0 truncate text-xs text-text-muted">{meta}</p>
          {task.description ? (
            <p className="min-w-0 break-words text-xs text-text-muted">{task.description}</p>
          ) : null}
        </div>
        <span className="inline-flex shrink-0 flex-wrap items-center justify-end gap-2 pt-0.5">
          <TaskActions task={task} onDeleted={onDeleted} />
        </span>
      </header>
      <SectionStack>
        <Section title={t("scheduledTasks.detail.what")}>
          <dl className="divide-y divide-border-subtle">
            <Row label={t("scheduledTasks.dialog.prompt")}>
              <span className="whitespace-pre-wrap">{c.prompt}</span>
            </Row>
            <Row label={t("scheduledTasks.dialog.session")}>{opens}</Row>
            <Row label={t("scheduledTasks.dialog.catchUp")}>
              {c.catch_up ? t("scheduledTasks.on") : t("scheduledTasks.off")}
            </Row>
            {c.template === "daily_report" ? (
              <Row label={t("scheduledTasks.detail.kind")}>
                {t("scheduledTasks.detail.dailyReport")}
              </Row>
            ) : null}
            {c.origin === "agent" ? (
              <Row label={t("scheduledTasks.detail.kind")}>
                {t("scheduledTasks.detail.followUp", {
                  index: c.chain_index ?? 1,
                  who: c.mention?.name || t("scheduledTasks.detail.theOwner"),
                })}
              </Row>
            ) : null}
          </dl>
        </Section>
        <TaskRuns uid={task.uid} />
      </SectionStack>
    </div>
  );
}
