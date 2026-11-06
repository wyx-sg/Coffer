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

/** Where a task runs: its chat's channel, or "No chat". */
export function whereText(t: TFunction, task: ScheduledTask): string {
  return task.config.chat ? task.channel_name : t("scheduledTasks.noChat");
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
    case "weekdays":
      return t("scheduledTasks.schedule.weekdaysAt", { time: schedule.time });
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
  replied: "ok",
  done: "ok",
  silent: "off",
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

/** The list's groups: what the owner set up, and the follow-ups agents booked. */
export function groupTasks(items: ScheduledTask[], filter: string) {
  const q = filter.trim().toLowerCase();
  const shown = q
    ? items.filter((task) =>
        [task.name, task.config.prompt, task.channel_name].some((s) => s.toLowerCase().includes(q)),
      )
    : items;
  return {
    mine: shown.filter((task) => task.config.origin !== "agent"),
    followUps: shown.filter((task) => task.config.origin === "agent"),
  };
}

// --- the form ----------------------------------------------------------------

export const SCHEDULE_KINDS: readonly ScheduleKind[] = [
  "daily",
  "weekdays",
  "weekly",
  "hourly",
  "once",
  "cron",
  "manual",
];

/** The Runs in choice for a task bound to no chat. */
export const NO_CHAT = "__no_chat__";

export interface TaskForm {
  name: string;
  /** `channel uid` + "\n" + `chat id`, or {@link NO_CHAT}; "" while none is picked. */
  chat: string;
  kind: ScheduleKind;
  time: string;
  minute: string;
  weekday: number;
  expr: string;
  /** The IANA zone a repeating schedule's times are read in; "" for this computer's. */
  timezone: string;
  /** A one-off task's moment, as a datetime-local input holds it. */
  at: string;
  prompt: string;
  session: "continue" | "fresh";
  agent: string;
  model: string;
  cwd: string;
  catchUp: boolean;
}

export function chatKey(channel: string, chatId: string): string {
  return `${channel}\n${chatId}`;
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
    chat: c ? (c.chat ? chatKey(c.chat.channel, c.chat.chat_id) : NO_CHAT) : "",
    kind: s?.kind ?? "daily",
    time: s && "time" in s ? s.time : "09:00",
    minute: String(s?.kind === "hourly" ? (s.minute ?? 0) : 0),
    weekday: s?.kind === "weekly" ? s.weekday : 0,
    expr: s?.kind === "cron" ? s.expr : "0 9 * * 1-5",
    timezone: s && "timezone" in s ? (s.timezone ?? "") : "",
    at: s?.kind === "once" ? localInput(s.at) : "",
    prompt: c?.prompt ?? "",
    session: c?.session ?? "fresh",
    agent: c?.agent ?? "",
    model: c?.model ?? "",
    cwd: c?.cwd ?? "",
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
    case "weekdays":
      return { kind: form.kind, time: form.time, ...timezone };
    case "weekly":
      return { kind: "weekly", weekday: form.weekday, time: form.time, ...timezone };
    case "cron":
      return { kind: "cron", expr: form.expr.trim(), ...timezone };
    case "manual":
      return { kind: "manual" };
  }
}

/** The config a form saves, over what the task already holds (a follow-up's
 *  chain and mention, the daily report's template, stay as they are). */
export function configFrom(form: TaskForm, base?: ScheduledTaskConfig): ScheduledTaskConfig {
  const noChat = form.chat === NO_CHAT;
  const [channel, chatId] = form.chat.split("\n");
  // A task in no chat has no conversation to carry on: every run is fresh.
  const session = noChat ? "fresh" : form.session;
  const fresh = session === "fresh";
  const sameChat = base?.chat && base.chat.channel === channel && base.chat.chat_id === chatId;
  const config: ScheduledTaskConfig = {
    ...base,
    schedule: scheduleFrom(form),
    prompt: form.prompt.trim(),
    chat: sameChat ? base.chat : { channel, chat_id: chatId },
    session,
    agent: fresh ? form.agent || null : null,
    model: fresh ? form.model.trim() || null : null,
    cwd: fresh ? form.cwd.trim() || null : null,
    catch_up: form.catchUp,
  };
  if (noChat) delete config.chat;
  return config;
}

export function formValid(form: TaskForm): boolean {
  if (!form.chat || !form.prompt.trim()) return false;
  // A task in no chat has no channel to fall back on: it names its agent.
  if (form.chat === NO_CHAT && !form.agent) return false;
  if (form.kind === "once") return form.at !== "" && !Number.isNaN(new Date(form.at).getTime());
  if (form.kind === "cron") return form.expr.trim().split(/\s+/).length === 5;
  return true;
}
