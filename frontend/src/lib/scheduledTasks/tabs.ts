// src/lib/scheduledTasks/tabs.ts — an open task's detail tabs, in order: Overview (the default, at the bare
// `/scheduled-tasks/<uid>`), Files (the task's folder, PROMPT.md included) and History, each at its own path
// segment like every detail page.
export const TASK_TABS = ["overview", "files", "runs"] as const;
export type TaskTab = (typeof TASK_TABS)[number];
export const DEFAULT_TASK_TAB: TaskTab = "overview";

export function taskBasePath(uid: string): string {
  return `/scheduled-tasks/${encodeURIComponent(uid)}`;
}
