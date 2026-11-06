// src/components/scheduled-tasks/WorkerRow.tsx — one of Coffer's own background workers in the list pane's Coffer internal section.
//
// Read-only: the worker's name in words and what it did last ("Every 5 min ·
// last 2 min ago", "Waits for changes", "Failed 3 times").
import { useTranslation } from "react-i18next";

import { StatusDot } from "@/components/status/StatusDot";
import type { DaemonWorker } from "@/lib/api/daemon";
import { useScrollIntoViewWhenCurrent } from "@/lib/hooks/useScrollIntoViewWhenCurrent";
import { workerLabel, workerTone } from "@/lib/scheduledTasks/format";
import { formatRelative } from "@/lib/time";
import { cn } from "@/lib/utils";

interface Props {
  worker: DaemonWorker;
  selected: boolean;
  onOpen: () => void;
}

export function WorkerRow({ worker, selected, onOpen }: Props) {
  const { t, i18n } = useTranslation();
  const rowRef = useScrollIntoViewWhenCurrent<HTMLButtonElement>(selected);
  const line =
    worker.state === "running"
      ? t("scheduledTasks.state.running")
      : worker.last_ok === false
        ? t("scheduledTasks.internal.failedLine")
        : worker.last_started_at
          ? t("scheduledTasks.internal.lastLine", {
              mode: t(`scheduledTasks.internal.mode.${worker.mode}`),
              last: formatRelative(worker.last_started_at, i18n.language, t),
            })
          : t(`scheduledTasks.internal.mode.${worker.mode}`);
  return (
    <li>
      <button
        type="button"
        ref={rowRef}
        aria-current={selected ? "page" : undefined}
        onClick={onOpen}
        className={cn(
          "flex min-h-[44px] w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <StatusDot tone={workerTone(worker)} size={6} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-text">{workerLabel(t, worker.name)}</span>
          <span
            className={cn(
              "block truncate text-xs",
              worker.last_ok === false ? "text-danger" : "text-text-muted",
            )}
          >
            {line}
          </span>
        </span>
      </button>
    </li>
  );
}
