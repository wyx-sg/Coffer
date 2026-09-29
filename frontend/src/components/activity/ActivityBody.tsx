// src/components/activity/ActivityBody.tsx — the visible tab's list in each of its states, and the strip above it.
//
// Loading is skeleton rows; a tab whose every log failed says so with Retry,
// while on Everything a failed log is named above the rows the others still
// show (spec web-ui "Query only the visible Activity tab and isolate
// failures"); nothing yet says what to do next, and filters that match
// nothing offer to clear them. The strip holds "↑ N new" while records wait.
import { Link } from "react-router-dom";
import { AlertCircle, ArrowUp, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { ActivityTab } from "@/lib/activity/records";
import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import { ActivityList } from "./ActivityList";
import type { AgentLook } from "./activityCells";

/** Whether every log the tab reads failed, so nothing at all can be shown. */
function everyLogFailed(feed: ActivityFeed): boolean {
  return feed.failed.length > 0 && feed.failed.length === feed.specs.length;
}

function useFailedNames(feed: ActivityFeed): string {
  const { t } = useTranslation();
  return feed.failed.map((s) => t(`activity.sources.${s.source}`)).join(", ");
}

/** A log that failed on a tab whose other logs still answered. */
export function PartialFailure({ feed }: { feed: ActivityFeed }) {
  const { t } = useTranslation();
  const names = useFailedNames(feed);
  if (feed.failed.length === 0 || everyLogFailed(feed)) return null;
  return (
    <Alert variant="error">
      <AlertCircle />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          <span className="font-label text-text">
            {t("activity.failed.title", { sources: names })}
          </span>{" "}
          {t("activity.failed.partial")}
        </span>
        <Button variant="outline" size="sm" onClick={() => feed.failed.forEach((s) => s.retry())}>
          {t("activity.failed.retry")}
        </Button>
      </div>
    </Alert>
  );
}

/** "↑ N new" while records are held; otherwise how many are loaded. */
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
  return (
    <div className="flex h-5 items-center justify-center text-2xs text-text-subtle">
      {held && feed.pendingCount > 0 ? (
        <button
          type="button"
          onClick={onShowNew}
          className="inline-flex h-6 items-center gap-1 rounded-full bg-accent px-2.5 text-xs font-semibold text-accent-foreground shadow-overlay"
        >
          <ArrowUp className="size-3" aria-hidden />
          {t("activity.pending", { count: feed.pendingCount })}
        </button>
      ) : (
        <span data-visual-volatile className="ml-auto">
          {feed.loaded > 0 ? t("activity.loaded", { count: feed.loaded }) : null}
        </span>
      )}
    </div>
  );
}

interface Props {
  tab: ActivityTab;
  feed: ActivityFeed;
  /** The filters narrow the view, so an empty list means "no match". */
  narrowed: boolean;
  onClearFilters: () => void;
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export function ActivityBody({
  tab,
  feed,
  narrowed,
  onClearFilters,
  agents,
  selectedKey,
  onSelect,
}: Props) {
  const { t } = useTranslation();
  const names = useFailedNames(feed);

  if (feed.isLoading) {
    return (
      <div className="flex flex-col gap-2 px-3 pt-3" aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    );
  }
  if (everyLogFailed(feed)) {
    return (
      <EmptyState
        tone="error"
        icon={AlertCircle}
        title={t("activity.failed.title", { sources: names })}
        description={translateApiError(t, feed.failed[0].error)}
        action={
          <Button variant="outline" onClick={() => feed.failed.forEach((s) => s.retry())}>
            {t("activity.failed.retry")}
          </Button>
        }
      />
    );
  }
  if (feed.rows.length === 0) {
    return narrowed ? (
      <EmptyState
        icon={ScrollText}
        title={t("activity.empty.noMatch")}
        description={t("activity.empty.noMatchBody")}
        action={
          <Button variant="outline" onClick={onClearFilters}>
            {t("activity.filters.clearAll")}
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={ScrollText}
        title={t("activity.empty.title")}
        description={t("activity.empty.body")}
        action={
          <Button asChild>
            <Link to="/agents">{t("activity.empty.connect")}</Link>
          </Button>
        }
        secondaryAction={
          <Button asChild variant="outline">
            <Link to="/mcp-servers">{t("activity.empty.addServer")}</Link>
          </Button>
        }
      />
    );
  }
  return (
    <>
      <ActivityList
        tab={tab}
        rows={feed.rows}
        agents={agents}
        selectedKey={selectedKey}
        onSelect={onSelect}
      />
      <div className="flex flex-wrap items-center gap-3 px-3 py-4">
        {feed.hasOlder ? (
          <Button
            variant="outline"
            size="sm"
            onClick={feed.loadOlder}
            disabled={feed.isLoadingOlder}
          >
            {feed.isLoadingOlder ? t("activity.loadingOlder") : t("activity.loadOlder")}
          </Button>
        ) : (
          <span className="text-xs text-text-subtle">{t("activity.end")}</span>
        )}
      </div>
    </>
  );
}
