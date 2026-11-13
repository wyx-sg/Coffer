// src/components/scheduled-tasks/TaskList.tsx — the Scheduled tasks list pane: a filter ("/" focuses it), then every task, soonest first.
//
// Spec scheduled-tasks "Manage scheduled tasks from the Scheduled tasks page".
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListLoadError, ListLoadingRows } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { filterTasks } from "@/lib/scheduledTasks/format";
import { TaskRow } from "./TaskRow";

interface Props {
  items: ScheduledTask[];
  loading: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** The open task's uid. */
  selected: string | null;
  onOpen: (uid: string) => void;
}

export function TaskList(props: Props) {
  const { items, loading, error, onRetry, selected, onOpen } = props;
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const rows = filterTasks(items, filter);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
      <SearchInput
        value={filter}
        onChange={setFilter}
        placeholder={t("scheduledTasks.search")}
        ariaLabel={t("scheduledTasks.search")}
        shortcut="/"
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <ListLoadError kind="scheduledTasks" error={error} onRetry={() => onRetry?.()} />
        ) : loading ? (
          <ListLoadingRows />
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-2 text-xs text-text-muted">
            {filter.trim() ? t("scheduledTasks.list.noMatch") : t("scheduledTasks.list.none")}
          </p>
        ) : (
          <ul aria-label={t("scheduledTasks.title")}>
            {rows.map((task) => (
              <TaskRow
                key={task.uid}
                task={task}
                selected={task.uid === selected}
                onOpen={() => onOpen(task.uid)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
