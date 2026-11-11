// src/lib/scheduledTasks/tabs.ts — an open task's detail tabs, in order: Overview (the default, at the bare
// `/scheduled-tasks/<uid>`), Prompt, History and Files (the task's folder), each at its own path segment
// like every detail page.
export const TASK_TABS = ["overview", "prompt", "runs", "files"] as const;
export type TaskTab = (typeof TASK_TABS)[number];
export const DEFAULT_TASK_TAB: TaskTab = "overview";

export function taskBasePath(uid: string): string {
  return `/scheduled-tasks/${encodeURIComponent(uid)}`;
}
