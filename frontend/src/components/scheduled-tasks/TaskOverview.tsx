// src/components/scheduled-tasks/TaskOverview.tsx — an open task's Overview tab: when it runs, and the agent,
// model and directory every run opens its new conversation with.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { AGENTS, scheduleText } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";

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
        <Row label={t("scheduledTasks.dialog.cwd")}>
          <span className="font-mono">{c.cwd || task.folder}</span>
        </Row>
        <Row label={t("scheduledTasks.dialog.catchUp")}>
          {c.catch_up ? t("scheduledTasks.on") : t("scheduledTasks.off")}
        </Row>
      </dl>
    </Section>
  );
}
