// src/lib/activity/recordText.ts — the small words an Activity row is made of: its clock time, its day, a call's outcome, an actor.
//
// Pure functions shared by the list, the drawer and their tests.
import type { TFunction } from "i18next";

import type { Invocation } from "./records";

function pad(n: number, width = 2): string {
  return String(n).padStart(width, "0");
}

/** "14:32:08" (or "14:32:08.126") in local time; "—" for a record nothing dates. */
export function clockTime(at: string | null, withMs = false): string {
  if (!at) return "—";
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "—";
  const base = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  return withMs ? `${base}.${pad(d.getMilliseconds(), 3)}` : base;
}

/** A call's outcome as the few words after its name ("failed — connection refused"). */
export function callOutcome(t: TFunction, call: Invocation): string {
  if (call.status === "ok") return "";
  if (call.status === "error") {
    return call.error_message
      ? t("activity.call.failedWith", { message: call.error_message })
      : t("activity.call.failed");
  }
  return t(`activity.call.${call.status}`);
}

/**
 * Who a change was made by, in words. The daemon's own background passes
 * record themselves as `system:<worker>`; to a reader every one of them is
 * Coffer.
 */
export function actorLabel(t: TFunction, actor: string): string {
  const base = actor.startsWith("system:") ? "system" : actor;
  return t(`activity.actor.${base}`, { defaultValue: actor });
}

/** "Today · 29 Sep", "Yesterday · 28 Sep" or "27 Sep" — the local day a record falls on. */
export function dayLabel(t: TFunction, at: string | null, now: Date, locale: string): string {
  if (!at) return t("activity.day.undated");
  const d = new Date(at);
  const date = d.toLocaleDateString(locale, { day: "numeric", month: "short" });
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(d)) / 86_400_000);
  if (days === 0) return t("activity.day.today", { date });
  if (days === 1) return t("activity.day.yesterday", { date });
  return date;
}
