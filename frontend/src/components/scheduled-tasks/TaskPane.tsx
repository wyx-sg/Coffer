// src/components/scheduled-tasks/TaskPane.tsx — the open task: its header and actions over two tabs.
//
// The header is the name with its state pill and one meta line (the agent ·
// the schedule in words · next run). The tabs, each at its own path segment:
// Overview (when it runs, what every run opens with, and the prompt, editable
// there) and History (every run, as a table).
import { CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusPill } from "@/components/status/StatusPill";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useDetailTab } from "@/lib/detailTabs";
import { STATE_TONE, agentText, scheduleText, taskState } from "@/lib/scheduledTasks/format";
import { DEFAULT_TASK_TAB, TASK_TABS, taskBasePath } from "@/lib/scheduledTasks/tabs";
import { formatMoment } from "@/lib/time";
import { TaskActions } from "./TaskActions";
import { TaskOverview } from "./TaskOverview";
import { TaskRuns } from "./TaskRuns";

interface Props {
  task: ScheduledTask;
  onDeleted: () => void;
}

export function TaskPane({ task, onDeleted }: Props) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useDetailTab(TASK_TABS, DEFAULT_TASK_TAB, taskBasePath(task.uid));
  const state = taskState(task);
  const c = task.config;
  const meta = [
    agentText(task),
    scheduleText(t, c.schedule, i18n.language),
    task.next_run
      ? t("scheduledTasks.detail.next", { next: formatMoment(task.next_run, i18n.language, t) })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
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
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {TASK_TABS.map((key) => (
            <TabsTrigger key={key} value={key}>
              {t(`scheduledTasks.tabs.${key}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview">
          <TaskOverview task={task} />
        </TabsContent>
        <TabsContent value="runs">
          <TaskRuns uid={task.uid} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
