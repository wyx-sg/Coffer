// src/components/scheduled-tasks/TaskList.tsx — the Scheduled tasks list pane: a filter ("/" focuses it), My tasks, Follow-ups, then Coffer internal.
//
// My tasks are the ones the owner set up (the daily report among them);
// Follow-ups the ones an agent booked in a thread. Coffer internal lists the
// daemon's own background workers, read-only: the featured ones, then the
// rest under Show all (spec daemon "Show Coffer's own background work beside
// the owner's tasks").
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListLoadError, ListLoadingRows } from "@/components/ListPaneStates";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import type { DaemonWorker } from "@/lib/api/daemon";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { groupTasks, orderWorkers, workerLabel } from "@/lib/scheduledTasks/format";
import { TaskRow } from "./TaskRow";
import { WorkerRow } from "./WorkerRow";

interface Props {
  items: ScheduledTask[];
  workers: DaemonWorker[];
  loading: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** The open task's uid, or `internal:<worker>`. */
  selected: string | null;
  onOpen: (uid: string) => void;
  onOpenWorker: (name: string) => void;
}

function Heading({ children }: { children: string }) {
  return (
    <h2
      aria-hidden
      className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted"
    >
      {children}
    </h2>
  );
}

export function TaskList(props: Props) {
  const { items, workers, loading, error, onRetry, selected, onOpen, onOpenWorker } = props;
  const { t } = useTranslation();
  const [filter, setFilter] = useState("");
  const [showAll, setShowAll] = useState(false);
  const { mine, followUps } = groupTasks(items, filter);
  const q = filter.trim().toLowerCase();
  const { featured, rest } = orderWorkers(
    q ? workers.filter((w) => workerLabel(t, w.name).toLowerCase().includes(q)) : workers,
  );
  const shownWorkers = showAll || q ? [...featured, ...rest] : featured;
  const groups = [
    { key: "mine", rows: mine },
    { key: "followUps", rows: followUps },
  ].filter((g) => g.key === "mine" || g.rows.length > 0);

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
        ) : (
          groups.map(({ key, rows }) => (
            <section key={key} className="mb-3" aria-label={t(`scheduledTasks.list.${key}`)}>
              <Heading>{t(`scheduledTasks.list.${key}`)}</Heading>
              {rows.length === 0 ? (
                <p className="px-2.5 py-2 text-xs text-text-muted">
                  {q ? t("scheduledTasks.list.noMatch") : t("scheduledTasks.list.none")}
                </p>
              ) : (
                <ul>
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
            </section>
          ))
        )}
        {shownWorkers.length > 0 ? (
          <section className="mb-3" aria-label={t("scheduledTasks.list.internal")}>
            <Heading>{t("scheduledTasks.list.internal")}</Heading>
            <ul>
              {shownWorkers.map((w) => (
                <WorkerRow
                  key={w.name}
                  worker={w}
                  selected={selected === `internal:${w.name}`}
                  onOpen={() => onOpenWorker(w.name)}
                />
              ))}
            </ul>
            {rest.length > 0 && !q ? (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 text-text-muted"
                onClick={() => setShowAll((v) => !v)}
              >
                {showAll
                  ? t("scheduledTasks.internal.showFewer")
                  : t("scheduledTasks.internal.showAll", { count: rest.length })}
              </Button>
            ) : null}
          </section>
        ) : null}
      </div>
    </div>
  );
}
