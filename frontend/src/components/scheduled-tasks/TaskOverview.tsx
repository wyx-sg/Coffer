// src/components/scheduled-tasks/TaskOverview.tsx — an open task's Overview tab: when it runs, the agent,
// model and folder every run opens its new conversation with, and under them the prompt (the task's
// PROMPT.md), rendered and editable in place. What a run writes stays in the folder: Reveal opens it in Finder.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { AGENTS, scheduleText } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";
import { TaskPromptFile } from "./TaskPromptFile";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 py-1.5 text-xs">
      <dt className="text-text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-text">{children}</dd>
    </div>
  );
}

export function TaskOverview({ task }: { task: ScheduledTask }) {
  const { t, i18n } = useTranslation();
  const c = task.config;
  const agent = AGENTS.find((a) => a.key === c.agent)?.label ?? c.agent;
  return (
    <div className="flex flex-col gap-5">
      <Section title={t("scheduledTasks.detail.what")}>
        <dl className="divide-y divide-border-subtle">
          <Row label={t("scheduledTasks.dialog.when")}>
            {scheduleText(t, c.schedule, i18n.language)}
          </Row>
          <Row label={t("scheduledTasks.detail.nextRun")}>
            {task.next_run ? formatMoment(task.next_run, i18n.language, t) : "—"}
          </Row>
          <Row label={t("scheduledTasks.dialog.agent")}>{agent}</Row>
          <Row label={t("scheduledTasks.dialog.model")}>
            {c.model || t("scheduledTasks.dialog.agentDefault")}
          </Row>
          <Row label={t("scheduledTasks.detail.folder")}>
            <span className="font-mono">{c.cwd || task.folder}</span>
            {c.cwd ? null : (
              <span className="ml-2 text-text-subtle">{t("scheduledTasks.detail.ownFolder")}</span>
            )}
          </Row>
          <Row label={t("scheduledTasks.dialog.catchUp")}>
            {c.catch_up ? t("scheduledTasks.on") : t("scheduledTasks.off")}
          </Row>
        </dl>
      </Section>
      <Section title={t("scheduledTasks.detail.prompt")}>
        <div className="flex min-h-48 flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface">
          <TaskPromptFile task={task} />
        </div>
      </Section>
    </div>
  );
}
