// src/components/activity/ActivityNotices.tsx — what Activity says around its rows: a log that failed, "↑ N new", and the box's footer.
//
// A failed log is one warning banner above the box, naming what is still
// complete, with Retry for the failed source only (design 6.2.03); it cannot
// be closed. "↑ N new" counts the records held while the reader is scrolled or
// has one open. The box's footer says how much is shown and what the next page
// holds; the retention note appears only once everything kept is shown (design
// 6.2.02).
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { LoadMoreSentinel } from "@/components/ui/load-more";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import {
  answered,
  everyLogFailed,
  failedNames,
  keptFor,
  sourceList,
} from "@/lib/activity/feedText";
import { clockTime } from "@/lib/activity/recordText";
import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import { MORE_PAGE } from "@/lib/hooks/useInfiniteList";
import { useRetentionPolicies } from "@/lib/hooks/useRetention";

/** A log that failed on a tab whose other logs still answered. */
export function PartialFailure({ feed }: { feed: ActivityFeed }) {
  const { t, i18n } = useTranslation();
  if (feed.failed.length === 0 || everyLogFailed(feed)) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-[10px] border border-warning/30 bg-warning-soft px-3.5 py-2.5"
    >
      <AlertTriangle className="size-[15px] shrink-0 text-warning" aria-hidden />
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-label text-text">
          {t("activity.failed.title", { sources: failedNames(t, feed) })}
        </span>
        <span className="text-xs text-text-muted">
          {translateApiError(t, feed.failed[0].error)}{" "}
          {t("activity.failed.partial", {
            sources: sourceList(t, i18n.language, answered(feed)),
          })}
        </span>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="ml-auto shrink-0"
        onClick={() => feed.failed.forEach((s) => s.retry())}
      >
        {t("activity.failed.retry")}
      </Button>
    </div>
  );
}

/** "↑ N new" while records are held. */
export function NewRecordsStrip({
  held,
  feed,
  onShowNew,
}: {
  held: boolean;
  feed: ActivityFeed;
  onShowNew: () => void;
}) {
  const { t } = useTranslation();
  if (!held || feed.pendingCount === 0) return null;
  return (
    <div className="-mt-1 mb-1.5 flex justify-center">
      <button
        type="button"
        onClick={onShowNew}
        className="inline-flex h-6 items-center gap-1 rounded-full bg-accent px-2.5 text-xs font-semibold text-accent-foreground shadow-overlay"
      >
        <ArrowUp className="size-3" aria-hidden />
        {t("activity.pending", { count: feed.pendingCount })}
      </button>
    </div>
  );
}

/** "That's everything kept. Tool calls are kept 30 days — Settings › Data". */
function RetentionNote() {
  const { t } = useTranslation();
  const policies = useRetentionPolicies().data?.policies ?? [];
  const calls = policies.find((p) => p.table_name === "mcp_invocations");
  return (
    <span className="text-xs text-text-subtle">
      {t("activity.end")}{" "}
      {t("activity.older.kept", { calls: keptFor(t, calls ? calls.retention_days : undefined) })}{" "}
      <Link to="/settings/data" className="text-text-muted underline-offset-2 hover:underline">
        {t("activity.older.settings")}
      </Link>
    </span>
  );
}

/**
 * The box's last row. While older records exist: "Showing N of M · next 50
 * from before 13:58" and "Load 50 more" (the page also loads when this
 * scrolls into view). At the end: the retention note.
 */
export function LoadOlder({ feed }: { feed: ActivityFeed }) {
  const { t, i18n } = useTranslation();
  const shown = feed.rows.length;
  const before = clockTime(feed.rows.at(-1)?.at ?? null).slice(0, 5);
  const total = feed.total ? feed.total.value.toLocaleString(i18n.language) : undefined;
  return (
    <div className="flex flex-col gap-2 border-t border-border-subtle px-3 py-2.5">
      {feed.isLoadingOlder ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-6 w-full" />
        </div>
      ) : null}
      {feed.hasOlder ? (
        <>
          <LoadMoreSentinel
            active={!feed.isLoadingOlder}
            onVisible={feed.loadOlder}
            version={shown}
          />
          <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
            <span data-visual-volatile="count">
              {total
                ? t("activity.older.showingOf", { shown, total })
                : t("activity.older.showing", { shown })}
              {" · "}
              {t("activity.older.next", { count: MORE_PAGE, before })}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              loading={feed.isLoadingOlder}
              onClick={feed.loadOlder}
            >
              {t("activity.loadOlder", { count: MORE_PAGE })}
            </Button>
          </div>
        </>
      ) : (
        <RetentionNote />
      )}
    </div>
  );
}
