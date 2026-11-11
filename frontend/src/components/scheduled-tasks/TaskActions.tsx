// src/components/scheduled-tasks/TaskActions.tsx — Run now, Pause / Resume, Edit and ⋯ › Delete in an open task's header.
//
// Run now starts the task at once, whatever its schedule (refused while it is
// already running). Pause and Resume switch the task off and on. Edit opens
// the same dialog as New task. Delete asks in a 420 confirm and closes only
// once the task is gone.
import { Pause, Pencil, Play, Zap } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ActionMenu } from "@/components/ui/menu";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import {
  useDeleteResource,
  useDisableResource,
  useEnableResource,
} from "@/lib/hooks/useResourceMutations";
import { SCHEDULED_TASK_KIND, useRunScheduledTask } from "@/lib/hooks/useScheduledTasks";
import { TaskDialog } from "./TaskDialog";

interface Props {
  task: ScheduledTask;
  onDeleted: () => void;
}

export function TaskActions({ task, onDeleted }: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const run = useRunScheduledTask();
  const enable = useEnableResource();
  const disable = useDisableResource();
  const remove = useDeleteResource();
  const write = { kind: SCHEDULED_TASK_KIND, uid: task.uid };
  // A task cannot run or resume before its PROMPT.md is written (the daemon refuses too).
  const noPrompt = task.prompt.trim() === "";
  const needsPrompt = noPrompt ? t("scheduledTasks.needsPrompt") : undefined;
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={noPrompt || task.running || run.isPending}
        title={needsPrompt}
        onClick={() => run.mutate(task.uid)}
      >
        <Zap aria-hidden />
        {t("scheduledTasks.runNow.action")}
      </Button>
      {task.enabled ? (
        <Button
          size="sm"
          variant="outline"
          disabled={disable.isPending}
          onClick={() => disable.mutate(write)}
        >
          <Pause aria-hidden />
          {t("scheduledTasks.pause")}
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={noPrompt || enable.isPending}
          title={needsPrompt}
          onClick={() => enable.mutate(write)}
        >
          <Play aria-hidden />
          {t("scheduledTasks.resume")}
        </Button>
      )}
      <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
        <Pencil aria-hidden />
        {t("common.edit")}
      </Button>
      <ActionMenu
        label={t("scheduledTasks.menu", { name: task.name })}
        actions={[
          {
            key: "delete",
            label: t("scheduledTasks.delete.action"),
            onSelect: () => setDeleting(true),
            destructive: true,
          },
        ]}
      />
      <TaskDialog open={editing} onOpenChange={setEditing} existing={task} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={t("scheduledTasks.delete.title", { name: task.name })}
        description={t("scheduledTasks.delete.body")}
        confirmLabel={t("scheduledTasks.delete.action")}
        pendingLabel={t("scheduledTasks.delete.pending")}
        errorTitle={t("scheduledTasks.delete.failed", { name: task.name })}
        variant="destructive"
        pending={remove.isPending}
        error={remove.error}
        onConfirm={() =>
          remove.mutate(write, {
            onSuccess: () => {
              setDeleting(false);
              onDeleted();
            },
          })
        }
      />
    </>
  );
}
