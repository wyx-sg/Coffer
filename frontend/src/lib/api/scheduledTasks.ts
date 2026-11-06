// frontend/src/lib/api/scheduledTasks.ts — request helpers for /api/v1/scheduled-tasks/*
// (spec channels "Manage scheduled tasks from the Scheduled tasks page").
//
// A task is a `scheduled_task` resource: editing, pausing, resuming, renaming
// and deleting ride the generic /resources routes (`resourcesApi`); these are
// a task's own reads and actions — the list with next and last runs, a task's
// run history, Run now, the chats a task may run in, and the daily report.
//
// Wire types are the channels contract's generated schemas.

import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/channels";

type Schemas = components["schemas"];

export type ScheduledTask = Schemas["ScheduledTaskOut"];
export type ScheduledRun = Schemas["ScheduledRunOut"];
export type ScheduledTaskConfig = Schemas["ScheduledTaskConfig"];
export type ScheduledTaskIn = Schemas["ScheduledTaskIn"];
export type Schedule = ScheduledTaskConfig["schedule"];
export type ScheduleKind = Schedule["kind"];
export type TaskChat = Schemas["TaskChatOut"];
export type RunOutcome = ScheduledRun["outcome"];
export type DailyReportIn = Schemas["DailyReportIn"];

export const scheduledTasksApi = {
  list: (): Promise<ScheduledTask[]> =>
    unwrap(getApiClient().GET("/scheduled-tasks")).then((r) => r.items),
  get: (uid: string): Promise<ScheduledTask> =>
    unwrap(getApiClient().GET("/scheduled-tasks/{uid}", { params: { path: { uid } } })),
  create: (body: ScheduledTaskIn): Promise<ScheduledTask> =>
    unwrap(getApiClient().POST("/scheduled-tasks", { body })),
  runs: (uid: string, limit = 50): Promise<ScheduledRun[]> =>
    unwrap(
      getApiClient().GET("/scheduled-tasks/{uid}/runs", {
        params: { path: { uid }, query: { limit } },
      }),
    ).then((r) => r.items),
  runNow: (uid: string): Promise<ScheduledRun> =>
    unwrap(getApiClient().POST("/scheduled-tasks/{uid}/run", { params: { path: { uid } } })),
  chats: (): Promise<TaskChat[]> =>
    unwrap(getApiClient().GET("/scheduled-tasks/chats")).then((r) => r.items),
  setDailyReport: (body: DailyReportIn): Promise<ScheduledTask> =>
    unwrap(getApiClient().PUT("/scheduled-tasks/daily-report", { body })),
};
