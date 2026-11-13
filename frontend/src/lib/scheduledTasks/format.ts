// src/lib/scheduledTasks/format.ts — what the Scheduled tasks page prints: a schedule in words, a run's tone, the list's groups, and the form ↔ config mapping.
//
// Spec channels "Manage scheduled tasks from the Scheduled tasks page".
import type { TFunction } from "i18next";

import type {
  RunOutcome,
  Schedule,
  ScheduleKind,
  ScheduledTask,
  ScheduledTaskConfig,
} from "@/lib/api/scheduledTasks";
import type { StatusTone } from "@/lib/statusTone";

/** A schedule in words: "Every day at 18:00", "Fridays at 17:30", with its
 *  timezone when it names one: "Every day at 11:00 (Asia/Singapore)". */
export function scheduleText(t: TFunction, schedule: Schedule, lang: string): string {
  const words = scheduleWords(t, schedule, lang);
  const zone = "timezone" in schedule ? schedule.timezone : null;
  return zone ? `${words} (${zone})` : words;
}

/** The agents a task may run on, by key, as the page names them. */
/** The longest prompt a task may carry (the daemon refuses more). */
export const PROMPT_MAX_LENGTH = 8000;

export const AGENTS = [
  { key: "claude_code", label: "Claude Code" },
  { key: "codex", label: "Codex" },
] as const;

/** The agent a task runs on, with its model when it names one. */
export function agentText(task: ScheduledTask): string {
  const c = task.config;
  const agent = AGENTS.find((a) => a.key === c.agent)?.label ?? c.agent;
  return c.model ? `${agent} · ${c.model}` : agent;
}

function scheduleWords(t: TFunction, schedule: Schedule, lang: string): string {
  switch (schedule.kind) {
    case "once":
      return t("scheduledTasks.schedule.onceAt", {
        when: new Date(schedule.at).toLocaleString(lang, {
          dateStyle: "medium",
          timeStyle: "short",
        }),
      });
    case "hourly":
      return t("scheduledTasks.schedule.hourlyAt", {
        minute: String(schedule.minute ?? 0).padStart(2, "0"),
      });
    case "daily":
      return t("scheduledTasks.schedule.dailyAt", { time: schedule.time });
    case "weekly":
      return t("scheduledTasks.schedule.weeklyAt", {
        day: weekdayName(schedule.weekday, lang),
        time: schedule.time,
      });
    case "cron":
      return t("scheduledTasks.schedule.cron", { expr: schedule.expr });
    case "manual":
      return t("scheduledTasks.schedule.manual");
  }
}

/** Monday is 0, as the daemon counts. */
export function weekdayName(weekday: number, lang: string): string {
  // 2024-01-01 was a Monday.
  return new Date(2024, 0, 1 + weekday).toLocaleDateString(lang, { weekday: "long" });
}

export const OUTCOME_TONE: Record<RunOutcome, StatusTone> = {
  running: "ok",
  done: "ok",
  skipped: "warn",
  failed: "err",
  stopped: "warn",
};

/** A task's state for its dot and pill: running, paused, failing or ready. */
export type TaskState = "running" | "paused" | "failed" | "done" | "ready";

export function taskState(task: ScheduledTask): TaskState {
  if (task.running) return "running";
  if (!task.enabled) return "paused";
  if (task.last_run?.outcome === "failed") return "failed";
  if (task.config.schedule.kind === "once" && task.next_run === null && task.last_run)
    return "done";
  return "ready";
}

export const STATE_TONE: Record<TaskState, StatusTone> = {
  running: "ok",
  ready: "ok",
  done: "off",
  paused: "off",
  failed: "err",
};

/** The tasks whose name or prompt holds the filter. */
export function filterTasks(items: ScheduledTask[], filter: string): ScheduledTask[] {
  const q = filter.trim().toLowerCase();
  return q
    ? items.filter((task) => [task.name, task.prompt].some((s) => s.toLowerCase().includes(q)))
    : items;
}

// --- the form ----------------------------------------------------------------

export const SCHEDULE_KINDS: readonly ScheduleKind[] = [
  "daily",
  "weekly",
  "hourly",
  "once",
  "cron",
  "manual",
];

export interface TaskForm {
  name: string;
  kind: ScheduleKind;
  time: string;
  minute: string;
  weekday: number;
  expr: string;
  /** The IANA zone a repeating schedule's times are read in; "" for this computer's. */
  timezone: string;
  /** A one-off task's moment, as a datetime-local input holds it. */
  at: string;
  agent: string;
  model: string;
  catchUp: boolean;
}

function localInput(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function formFrom(task?: ScheduledTask): TaskForm {
  const c = task?.config;
  const s = c?.schedule;
  return {
    name: task?.name ?? "",
    kind: s?.kind ?? "daily",
    time: s && "time" in s ? s.time : "09:00",
    minute: String(s?.kind === "hourly" ? (s.minute ?? 0) : 0),
    weekday: s?.kind === "weekly" ? s.weekday : 0,
    expr: s?.kind === "cron" ? s.expr : "0 9 * * 1-5",
    timezone: s && "timezone" in s ? (s.timezone ?? "") : "",
    at: s?.kind === "once" ? localInput(s.at) : "",
    agent: c?.agent ?? "claude_code",
    model: c?.model ?? "",
    catchUp: c?.catch_up ?? true,
  };
}

function scheduleFrom(form: TaskForm): Schedule {
  const zone = form.timezone.trim();
  const timezone = zone ? { timezone: zone } : {};
  switch (form.kind) {
    case "once":
      return { kind: "once", at: new Date(form.at).toISOString() };
    case "hourly":
      return { kind: "hourly", minute: Number(form.minute) || 0, ...timezone };
    case "daily":
      return { kind: "daily", time: form.time, ...timezone };
    case "weekly":
      return { kind: "weekly", weekday: form.weekday, time: form.time, ...timezone };
    case "cron":
      return { kind: "cron", expr: form.expr.trim(), ...timezone };
    case "manual":
      return { kind: "manual" };
  }
}

/** The config a form saves. */
export function configFrom(form: TaskForm): ScheduledTaskConfig {
  return {
    schedule: scheduleFrom(form),
    agent: form.agent,
    model: form.model.trim() || null,
    catch_up: form.catchUp,
  };
}

/** Whether the form can be saved: a name and an agent (the prompt is written in the Files tab). */
export function formValid(form: TaskForm): boolean {
  if (!form.name.trim() || !form.agent) return false;
  if (form.kind === "once") return form.at !== "" && !Number.isNaN(new Date(form.at).getTime());
  if (form.kind === "cron") return form.expr.trim().split(/\s+/).length === 5;
  return true;
}
