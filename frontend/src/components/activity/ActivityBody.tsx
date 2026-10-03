// src/components/activity/ActivityBody.tsx — the visible tab's list in each of its states.
//
// Loading is skeleton rows; a tab whose every log failed says so with Retry
// (spec web-ui "Query only the visible Activity tab and isolate failures");
// filters that match nothing offer to clear them; a time range with nothing in
// it says so. When Coffer has recorded nothing at all the page shows the first
// run instead (design 6.2.09, `FirstRun`). Otherwise the rows in their box,
// with the next page's footer as its last row (design 6.2.01, 6.2.02).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, RotateCw, Activity } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { everyLogFailed, failedNames } from "@/lib/activity/feedText";
import type { ActivityRecord, ActivityTab } from "@/lib/activity/records";
import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import type { TableSort } from "@/lib/tableSort";
import { ActivityList } from "./ActivityList";
import { LoadOlder } from "./ActivityNotices";
import type { AgentLook } from "./activityCells";

/** Nothing has been recorded at all: the whole-page empty state. */
export function FirstRun() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={Activity}
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

interface Props {
  tab: ActivityTab;
  feed: ActivityFeed;
  /** The filters narrow the view, so an empty list means "no match". */
  narrowed: boolean;
  onClearFilters: () => void;
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  sort: TableSort | null;
  onSort: (sort: TableSort | null) => void;
  /** What an open Daemon log row shows under itself. */
  renderExpanded?: (r: ActivityRecord) => ReactNode;
}

export function ActivityBody({
  tab,
  feed,
  narrowed,
  onClearFilters,
  agents,
  selectedKey,
  onSelect,
  sort,
  onSort,
  renderExpanded,
}: Props) {
  const { t } = useTranslation();

  if (feed.isLoading) {
    return (
      <div className="flex flex-col gap-2 pt-1" aria-busy="true">
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
        title={t("activity.failed.title", { sources: failedNames(t, feed) })}
        description={translateApiError(t, feed.failed[0].error)}
        action={
          <Button variant="outline" onClick={() => feed.failed.forEach((s) => s.retry())}>
            <RotateCw />
            {t("activity.failed.retry")}
          </Button>
        }
      />
    );
  }
  // Everything loaded so far is hidden by a client-side filter or the merge
  // frontier, and older records exist: keep reading rather than say "none".
  if (feed.rows.length === 0 && feed.hasOlder) {
    return (
      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <LoadOlder feed={feed} />
      </div>
    );
  }
  if (feed.rows.length === 0) {
    return narrowed ? (
      <EmptyState
        icon={Activity}
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
        icon={Activity}
        title={t("activity.empty.window")}
        description={t("activity.empty.windowBody")}
      />
    );
  }
  return (
    <ActivityList
      tab={tab}
      rows={feed.rows}
      agents={agents}
      selectedKey={selectedKey}
      onSelect={onSelect}
      sort={sort}
      onSort={onSort}
      renderExpanded={renderExpanded}
      footer={<LoadOlder feed={feed} />}
    />
  );
}
