// src/lib/overview/tileText.ts — the small phrases the Health tiles' detail lines are made of.
//
// "14 min ago", "edited today 13:30", "SeaTalk reconnecting since 13:41" and a
// list of names. Times follow the app's own helpers (lib/overview/time,
// lib/time) so a clock reads the same here as on a Needs you row.
import type { TFunction } from "i18next";

import { formatClockOrMoment, formatDay } from "@/lib/time";
import { describeAgo } from "./time";

/** "14 min ago", "3 h ago", "2 d ago", "just now"; null for no or a malformed time. */
export function agoText(t: TFunction, iso: string | null, now: Date = new Date()): string | null {
  const ago = describeAgo(iso, now);
  if (!ago) return null;
  return ago.unit === "now"
    ? t("overview.health.ago.now")
    : t(`overview.health.ago.${ago.unit}`, { count: ago.count });
}

/** "edited today 13:30" for today, "edited 28 Sep" for another day; null for no or a malformed time. */
export function editedText(
  t: TFunction,
  lang: string,
  iso: string | null,
  now: Date = new Date(),
): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const today = at.toDateString() === now.toDateString();
  return today
    ? t("overview.health.editedToday", { time: formatClockOrMoment(at, lang, t, now) })
    : t("overview.health.edited", { day: formatDay(at, lang) });
}

/** "SeaTalk reconnecting since 13:41" (a day's moment when it began on another day). */
export function reconnectingText(
  t: TFunction,
  lang: string,
  name: string,
  since: string | null,
  now: Date = new Date(),
): string {
  const at = since ? new Date(since) : null;
  if (!at || Number.isNaN(at.getTime()))
    return t("overview.health.channels.reconnecting", { name });
  return t("overview.health.channels.reconnectingSince", {
    name,
    time: formatClockOrMoment(at, lang, t, now),
  });
}

/** Every name, " · " between; the tile truncates what does not fit. */
export function joinNames(list: readonly { name: string; title?: string | null }[]): string {
  return list.map((x) => x.title || x.name).join(" · ");
}

/** The latest of some ISO times, or null when there are none. */
export function latest(times: readonly (string | null | undefined)[]): string | null {
  let best: string | null = null;
  let bestMs = -Infinity;
  for (const time of times) {
    const ms = time ? Date.parse(time) : NaN;
    if (!Number.isNaN(ms) && ms > bestMs) {
      best = time as string;
      bestMs = ms;
    }
  }
  return best;
}
