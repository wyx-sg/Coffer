// src/lib/activity/recordText.ts — the small words an Activity row is made of: its clock time, its day, a call's outcome, an actor.
//
// Pure functions shared by the list, the drawer and their tests.
import type { TFunction } from "i18next";

import { agentBasePath } from "@/lib/agents/routes";

import {
  callServerLabel,
  recordTimeMs,
  type ActivityRecord,
  type AuditEntry,
  type Invocation,
} from "./records";

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

/** The route a change's resource lives at, when it has a page of its own. */
/** The kinds whose detail page is addressed by uid, which an audit entry does not carry. */
export const UID_ADDRESSED_KINDS: readonly string[] = ["provider", "channel", "knowledge"];

/**
 * Where a change's "Open X" goes: the resource's own detail page. A kind whose
 * page is addressed by uid needs `uid` (looked up from its name by the caller);
 * without it the link falls back to the kind's list.
 */
export function changeLink(entry: AuditEntry, uid?: string): { to: string; name: string } | null {
  const name = entry.resource_name;
  if (!name) return null;
  const byUid = (base: string) => (uid ? `${base}/${encodeURIComponent(uid)}` : base);
  switch (entry.resource_kind) {
    case "mcp_server":
      return { to: `/mcp-servers/${encodeURIComponent(name)}`, name };
    case "skill":
      return { to: `/skills/${encodeURIComponent(name)}`, name };
    case "agent":
      // An agent is named by its type in resource style (`claude-code`); its page by the type.
      return { to: agentBasePath(name.replace(/-/g, "_")), name };
    case "provider":
      return { to: byUid("/model-providers"), name };
    case "channel":
      return { to: byUid("/channels"), name };
    case "knowledge":
      return { to: byUid("/knowledge"), name };
    default:
      return null;
  }
}

/** "You, in the web UI", "Coffer", "Sync" — who made a change, said in full. */
export function actorLong(t: TFunction, actor: string): string {
  const base = actor.startsWith("system:") ? "system" : actor;
  return t(`activity.actorLong.${base}`, { defaultValue: actorLabel(t, actor) });
}

/** "14:32:08.114 today" — when a record was written, for the drawer's header. */
export function whenLabel(
  t: TFunction,
  at: string | null,
  withMs: boolean,
  locale: string,
): string {
  if (!at) return "";
  const time = clockTime(at, withMs);
  const now = new Date();
  const day = dayLabel(t, at, now, locale);
  if (day === dayLabel(t, now.toISOString(), now, locale)) {
    return t("activity.drawer.whenToday", { time });
  }
  const yesterday = new Date(now.getTime() - 86_400_000).toISOString();
  if (day === dayLabel(t, yesterday, now, locale)) {
    return t("activity.drawer.whenYesterday", { time });
  }
  const date = new Date(at).toLocaleDateString(locale, { day: "numeric", month: "short" });
  return t("activity.drawer.whenOn", { time, date });
}

/** Records this close to an open one count as "around the same time". */
const AROUND_MS = 5 * 60_000;

/** The records written within five minutes of `record`, nearest first, at most three. */
export function nearby(record: ActivityRecord, rows: readonly ActivityRecord[]): ActivityRecord[] {
  const at = recordTimeMs(record.at);
  if (!at) return [];
  return rows
    .filter((r) => r.key !== record.key && r.at && Math.abs(recordTimeMs(r.at) - at) <= AROUND_MS)
    .sort((a, b) => Math.abs(recordTimeMs(a.at) - at) - Math.abs(recordTimeMs(b.at) - at))
    .slice(0, 3);
}

/** "+13 s", "−2 min" — how far another record is from this one. */
export function offsetLabel(t: TFunction, from: ActivityRecord, to: ActivityRecord): string {
  const seconds = Math.round((recordTimeMs(to.at) - recordTimeMs(from.at)) / 1000);
  const sign = seconds >= 0 ? "+" : "−";
  const abs = Math.abs(seconds);
  return abs < 60
    ? t("activity.drawer.offsetSeconds", { sign, n: abs })
    : t("activity.drawer.offsetMinutes", { sign, n: Math.round(abs / 60) });
}

/** A failure that says the server could not be reached, rather than that a tool failed. */
const UNREACHABLE = /refused|unreachable|connect|timed? ?out|dns|resolve|reset/i;

/** The headline of a call that did not go well: "Couldn't reach sentry". */
export function callProblemTitle(t: TFunction, call: Invocation): string {
  const server = callServerLabel(call);
  if (call.status === "error" && call.error_message && UNREACHABLE.test(call.error_message)) {
    return t("activity.drawer.callProblem.unreachable", { server });
  }
  return t(`activity.drawer.callProblem.${call.status}`, { server });
}

/** "sentry has been failing since 14:20 — 7 errors in the last 24 hours." */
export function serverFailureLine(
  t: TFunction,
  call: Invocation,
  failures: { failingSince: string | null; errors: number } | undefined,
): string | null {
  if (!failures) return null;
  if (failures.failingSince) {
    return t("activity.drawer.failingSince", {
      server: callServerLabel(call),
      since: clockTime(failures.failingSince).slice(0, 5),
      count: failures.errors,
    });
  }
  return failures.errors ? t("activity.drawer.errorsToday", { count: failures.errors }) : null;
}
