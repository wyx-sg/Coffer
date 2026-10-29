// src/pages/ScheduledTasksPage.tsx — the Scheduled tasks page (/scheduled-tasks, /scheduled-tasks/:uid, /scheduled-tasks/internal/:worker).
//
// Spec channels "Manage scheduled tasks from the Scheduled tasks page" and
// daemon "Show Coffer's own background work beside the owner's tasks". The
// list pane holds the owner's tasks (theirs, then the follow-ups agents
// booked) and, read-only, Coffer's own background workers; the detail pane
// shows the one in the address, or the first task when there is none. The
// header holds New task.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { TaskDialog } from "@/components/scheduled-tasks/TaskDialog";
import { TaskList } from "@/components/scheduled-tasks/TaskList";
import { TaskPane } from "@/components/scheduled-tasks/TaskPane";
import { WorkerPane } from "@/components/scheduled-tasks/WorkerPane";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { Button } from "@/components/ui/button";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useScheduledTasks } from "@/lib/hooks/useScheduledTasks";
import { cn } from "@/lib/utils";

export function ScheduledTasksPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { uid, worker } = useParams<{ uid?: string; worker?: string }>();
  const { data, isPending, error, refetch } = useScheduledTasks();
  const workers = useDaemonStatus().data?.runtime?.workers ?? [];
  const [adding, setAdding] = useState(false);
  const items = data ?? [];
  const openUid = worker ? null : (uid ?? items[0]?.uid ?? null);
  const task = openUid ? items.find((x) => x.uid === openUid) : undefined;
  const openWorker = worker ? workers.find((w) => w.name === worker) : undefined;
  const selected = worker ? `internal:${worker}` : openUid;

  let detail: JSX.Element | null = null;
  if (openWorker) detail = <WorkerPane worker={openWorker} />;
  else if (task)
    detail = <TaskPane key={task.uid} task={task} onDeleted={() => navigate("/scheduled-tasks")} />;
  else if (!isPending && !error && items.length === 0 && !worker)
    detail = (
      <div className="flex h-full flex-col items-center justify-center gap-3 pb-20 text-center">
        <h2 className="text-md font-semibold text-text">{t("scheduledTasks.empty.title")}</h2>
        <p className="max-w-sm text-sm text-text-muted">{t("scheduledTasks.empty.body")}</p>
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          {t("scheduledTasks.newTask")}
        </Button>
      </div>
    );

  return (
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "flex shrink-0 flex-col gap-1.5 pb-5")}>
        <PageHeader
          title={t("scheduledTasks.title")}
          subtitle={t("scheduledTasks.subtitle")}
          actions={
            <Button onClick={() => setAdding(true)}>
              <Plus aria-hidden />
              {t("scheduledTasks.newTask")}
            </Button>
          }
        />
      </div>
      <SplitView
        storageKey="scheduledTasks.list"
        defaultListWidth={320}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        listClassName="bg-surface-sidebar"
        detailClassName="overflow-y-auto"
        list={
          <TaskList
            items={items}
            workers={workers}
            loading={isPending}
            error={error}
            onRetry={() => void refetch()}
            selected={selected}
            onOpen={(id) => navigate(`/scheduled-tasks/${encodeURIComponent(id)}`)}
            onOpenWorker={(name) =>
              navigate(`/scheduled-tasks/internal/${encodeURIComponent(name)}`)
            }
          />
        }
        detail={<div className="h-full px-7 py-5">{detail}</div>}
      />
      <TaskDialog
        open={adding}
        onOpenChange={setAdding}
        onSaved={(id) => navigate(`/scheduled-tasks/${encodeURIComponent(id)}`)}
      />
    </div>
  );
}
