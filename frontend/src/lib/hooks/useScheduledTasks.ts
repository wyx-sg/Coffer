// src/lib/hooks/useScheduledTasks.ts — TanStack Query bindings for the Scheduled tasks page (/scheduled-tasks).
//
// Reads: the task list (with each task's next and last run) and one task's run
// history. Writes: create, edit (the generic resource PATCH) and Run now.
// Pause, resume and
// delete are the generic resource mutations with kind `scheduled_task`, which
// refresh this list through `ownListKeysForKind`.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  resourcesKey,
  scheduledTaskRunsKey,
  scheduledTasksKey,
} from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import {
  scheduledTasksApi,
  type ScheduledTaskConfig,
  type ScheduledTaskIn,
} from "@/lib/api/scheduledTasks";

export const SCHEDULED_TASK_KIND = "scheduled_task";

export function useScheduledTasks() {
  return useQuery({
    queryKey: scheduledTasksKey,
    queryFn: () => scheduledTasksApi.list(),
    // Next and last runs move on their own; a running task finishes.
    refetchInterval: 30_000,
  });
}

export function useScheduledTaskRuns(uid: string) {
  return useQuery({
    queryKey: scheduledTaskRunsKey(uid),
    queryFn: () => scheduledTasksApi.runs(uid),
    enabled: !!uid,
    refetchInterval: 30_000,
  });
}

function useRefresh() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: scheduledTasksKey });
    void qc.invalidateQueries({ queryKey: resourcesKey });
  };
}

export function useCreateScheduledTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: ScheduledTaskIn) => scheduledTasksApi.create(body),
    onSuccess: refresh,
  });
}

/** @ui-only — the hook's own argument: the PATCH body is built from it. */
export interface TaskEdit {
  uid: string;
  name: string;
  config: ScheduledTaskConfig;
}

export function useEditScheduledTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ uid, name, config }: TaskEdit) =>
      resourcesApi.update(uid, { name, config: config as Record<string, unknown> }),
    onSuccess: refresh,
  });
}

export function useRunScheduledTask() {
  const refresh = useRefresh();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (uid: string) => scheduledTasksApi.runNow(uid),
    onSuccess: () => {
      refresh();
      toast.success(t("scheduledTasks.runNow.started"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
