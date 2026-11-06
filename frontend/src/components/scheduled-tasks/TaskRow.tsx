// src/components/scheduled-tasks/TaskRow.tsx — one task in the Scheduled tasks list pane (board TaskList): a state dot, its name, and when it runs next.
//
// The second line is the schedule in words and the next run ("Every day at
// 18:00 · next today at 18:00"), "Running now" while it runs, "Paused" when it
// is switched off, or how its last run failed.
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useScrollIntoViewWhenCurrent } from "@/lib/hooks/useScrollIntoViewWhenCurrent";
import { STATE_TONE, scheduleText, taskState } from "@/lib/scheduledTasks/format";
import { formatMoment } from "@/lib/time";
import { cn } from "@/lib/utils";

interface Props {
  task: ScheduledTask;
  selected: boolean;
  onOpen: () => void;
}

function useLine(task: ScheduledTask): string {
  const { t, i18n } = useTranslation();
  const state = taskState(task);
  if (state === "running") return t("scheduledTasks.state.running");
  if (state === "paused") return t("scheduledTasks.list.pausedLine");
  if (state === "failed")
    return t("scheduledTasks.list.failedLine", { reason: task.last_run?.reason || "" });
  const when = scheduleText(t, task.config.schedule, i18n.language);
  if (!task.next_run) return when;
  return t("scheduledTasks.list.nextLine", {
    when,
    next: formatMoment(task.next_run, i18n.language, t),
  });
}

export function TaskRow({ task, selected, onOpen }: Props) {
  const rowRef = useScrollIntoViewWhenCurrent<HTMLButtonElement>(selected);
  const line = useLine(task);
  const state = taskState(task);
  return (
    <li>
      <button
        type="button"
        ref={rowRef}
        aria-current={selected ? "page" : undefined}
        onClick={onOpen}
        className={cn(
          "flex min-h-[52px] w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <StatusDot tone={STATE_TONE[state]} size={6} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-label text-text">{task.name}</span>
          <span
            className={cn(
              "block truncate text-xs",
              state === "failed" ? "text-danger" : "text-text-muted",
            )}
          >
            {line}
          </span>
        </span>
      </button>
    </li>
  );
}
