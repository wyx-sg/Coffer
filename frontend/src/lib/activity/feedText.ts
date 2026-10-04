// src/lib/activity/feedText.ts — what the Activity list says about itself: which logs answered, and how long records are kept.
//
// Pure functions over the visible tab's feed, shared by the partial-failure
// banner and the load-older footer (design 6.2.02, 6.2.03).
import type { TFunction } from "i18next";

import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import type { ActivitySource } from "./records";

/** Whether every log the tab reads failed, so nothing at all can be shown. */
export function everyLogFailed(feed: ActivityFeed): boolean {
  return feed.failed.length > 0 && feed.failed.length === feed.specs.length;
}

/** The names of the logs that failed, for the notice's title. */
export function failedNames(t: TFunction, feed: ActivityFeed): string {
  return feed.failed.map((s) => t(`activity.sources.${s.source}`)).join(", ");
}

/** The sources this tab reads that answered. */
export function answered(feed: ActivityFeed): ActivitySource[] {
  const failed = new Set(feed.failed.map((s) => s.source));
  return feed.specs.map((s) => s.source).filter((s) => !failed.has(s));
}

/** "Changes and daemon records" — sources as a list in the reader's language. */
export function sourceList(
  t: TFunction,
  locale: string,
  sources: ActivitySource[],
  capitalise = true,
): string {
  const names = sources.map((s) => t(`activity.summary.sources.${s}`));
  const text = new Intl.ListFormat(locale, { type: "conjunction" }).format(names);
  return capitalise ? text.charAt(0).toLocaleUpperCase(locale) + text.slice(1) : text;
}

/** "30 days", "1 year", "forever" — how long a retention policy keeps its rows. */
export function keptFor(t: TFunction, days: number | null | undefined): string {
  if (days === null) return t("activity.older.forever");
  if (days === undefined) return "—";
  if (days % 365 === 0) return t("activity.older.years", { count: days / 365 });
  return t("activity.older.days", { count: days });
}
