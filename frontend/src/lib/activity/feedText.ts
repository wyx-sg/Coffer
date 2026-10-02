// src/lib/activity/feedText.ts — what the Activity list says about itself: which logs answered, and the line above the rows.
//
// Pure functions over the visible tab's feed, shared by the list's notices
// and its summary line (design 6.1: "1 error and 1 warning in the last hour"
// once the list is whole, "30 loaded of 1,204" while it is not, "182 calls · 7
// failed · 1 denied", "Changes and daemon records").
import type { TFunction } from "i18next";

import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import { recordSeverity, type ActivitySource, type ActivityTab } from "./records";

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

/** The line above the rows: what the visible tab holds, or null when nothing is known yet. */
export function listSummary(
  t: TFunction,
  locale: string,
  tab: ActivityTab,
  feed: ActivityFeed,
  timeRange: string,
): string | null {
  const n = (value: number) => value.toLocaleString(locale);
  if (feed.failed.length > 0) return sourceList(t, locale, answered(feed));
  const total = feed.counts[tab].value;
  if (tab === "mcp") {
    if (total === undefined) return null;
    const calls = t("activity.summary.calls", { count: total, n: n(total) });
    if (!feed.callTally) return calls;
    const { failed, denied } = feed.callTally;
    return [
      calls,
      t("activity.summary.failed", { count: failed, n: n(failed) }),
      t("activity.summary.denied", { count: denied, n: n(denied) }),
    ].join(" · ");
  }
  // A page is a slice of the log: a tally of its errors and warnings would
  // read as the log's own. Until every record is loaded the line says how many
  // are, and the tally appears once the list is whole.
  if (feed.hasOlder) {
    if (total === undefined || feed.loaded === 0) return null;
    return t("activity.summary.loadedOf", { loaded: n(feed.loaded), total: n(total) });
  }
  const errors = feed.rows.filter((r) => recordSeverity(r) === "error").length;
  const warnings = feed.rows.filter((r) => recordSeverity(r) === "warning").length;
  if (errors || warnings) {
    const parts = [
      ...(errors ? [t("activity.summary.errors", { count: errors, n: n(errors) })] : []),
      ...(warnings ? [t("activity.summary.warnings", { count: warnings, n: n(warnings) })] : []),
    ];
    const problems = new Intl.ListFormat(locale, { type: "conjunction" }).format(parts);
    const range = t(`activity.time.phrase.${timeRange}`, { defaultValue: "" });
    return t("activity.summary.problems", { problems, range }).trim();
  }
  if (total === undefined || feed.loaded === 0) return null;
  if (feed.loaded >= total) return t("activity.summary.all", { count: total, n: n(total) });
  return t("activity.summary.loadedOf", { loaded: n(feed.loaded), total: n(total) });
}
