// src/components/activity/ActivityNotices.tsx — what Activity says around its rows: a log that failed, "↑ N new", and what "Load older" brings.
//
// On Everything a failed log is named above the rows the others still show,
// with its error, what is still shown and Retry (design 6.1.06); "↑ N new"
// counts the records held while the reader is scrolled or has one open; and
// beside "Load older" the page says what the next page holds and how long
// each record is kept (design 6.1.02).
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowUp, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { LoadMoreFooter } from "@/components/ui/load-more";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import {
  answered,
  everyLogFailed,
  failedNames,
  keptFor,
  sourceList,
} from "@/lib/activity/feedText";
import type { ActivityRecord } from "@/lib/activity/records";
import { clockTime } from "@/lib/activity/recordText";
import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import { MORE_PAGE } from "@/lib/hooks/useInfiniteList";
import { useRetentionPolicies } from "@/lib/hooks/useRetention";

/** A log that failed on a tab whose other logs still answered. */
export function PartialFailure({ feed }: { feed: ActivityFeed }) {
  const { t, i18n } = useTranslation();
  const names = failedNames(t, feed);
  if (feed.failed.length === 0 || everyLogFailed(feed)) return null;
  return (
    <div role="status" className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3 py-2.5">
      <AlertTriangle className="mt-px size-[15px] shrink-0 text-warning" aria-hidden />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-sm font-label text-text">
          {t("activity.failed.title", { sources: names })}
        </span>
        <span className="text-xs leading-[1.45] text-text-muted">
          {translateApiError(t, feed.failed[0].error)}{" "}
          {t("activity.failed.partial", {
            sources: sourceList(t, i18n.language, answered(feed), false),
          })}
        </span>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="ml-auto shrink-0"
        onClick={() => feed.failed.forEach((s) => s.retry())}
      >
        <RotateCw />
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

function OlderHint({ oldest }: { oldest: ActivityRecord | undefined }) {
  const { t } = useTranslation();
  const policies = useRetentionPolicies().data?.policies ?? [];
  const days = (table: string) => {
    const p = policies.find((x) => x.table_name === table);
    return p ? p.retention_days : undefined;
  };
  return (
    <span className="text-xs text-text-subtle">
      {t("activity.older.hint", {
        count: MORE_PAGE,
        before: clockTime(oldest?.at ?? null).slice(0, 5),
        calls: keptFor(t, days("mcp_invocations")),
        changes: keptFor(t, days("audit_log")),
      })}{" "}
      <Link to="/settings/data" className="text-text-muted underline-offset-2 hover:underline">
        {t("activity.older.settings")}
      </Link>
      .
    </span>
  );
}

/**
 * Under the rows: the next page loads when this scrolls into view (a skeleton
 * row stands in for it), and "N loaded · Load more" is the same thing by hand.
 */
export function LoadOlder({ feed }: { feed: ActivityFeed }) {
  const { t } = useTranslation();
  const loaded = feed.rows.length;
  return (
    <div className="flex flex-col gap-3 px-3 py-4">
      {feed.isLoadingOlder ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
        </div>
      ) : null}
      {feed.hasOlder ? (
        <LoadMoreFooter
          autoLoad
          loaded={loaded}
          hasMore
          loading={feed.isLoadingOlder}
          onMore={feed.loadOlder}
          moreLabel={t("activity.loadOlder")}
          hint={<OlderHint oldest={feed.rows.at(-1)} />}
        />
      ) : (
        <span className="text-xs text-text-subtle">{t("activity.end")}</span>
      )}
    </div>
  );
}
