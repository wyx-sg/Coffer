// src/components/activity/ActivityBody.tsx — the visible tab's list in each of its states.
//
// Loading is skeleton rows; a tab whose every log failed says so with Retry
// (spec web-ui "Query only the visible Activity tab and isolate failures");
// nothing yet says what to do next, and filters that match nothing offer to
// clear them. Otherwise the rows, with the line above them saying what the
// list holds, and under them the next page — loaded when scrolled to, or by
// "Load more" (design 6.1.01, 6.1.02, 6.1.10).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, RotateCw, Activity } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { everyLogFailed, failedNames, listSummary } from "@/lib/activity/feedText";
import type { ActivityRecord, ActivityTab } from "@/lib/activity/records";
import type { ActivityFeed } from "@/lib/hooks/useActivityFeed";
import { ActivityList } from "./ActivityList";
import { LoadOlder } from "./ActivityNotices";
import type { AgentLook } from "./activityCells";

interface Props {
  tab: ActivityTab;
  feed: ActivityFeed;
  /** The filters narrow the view, so an empty list means "no match". */
  narrowed: boolean;
  onClearFilters: () => void;
  agents: ReadonlyMap<string, AgentLook>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
  /** The time window's key and its words, for the summary and the MCP calls line. */
  timeRange: string;
  windowLabel: string;
  /** What an open Daemon log row shows under itself. */
  renderExpanded?: (r: ActivityRecord) => ReactNode;
  /** Above the Daemon log's rows: the file it reads and whether it follows it. */
  logLine?: ReactNode;
}

export function ActivityBody({
  tab,
  feed,
  narrowed,
  onClearFilters,
  agents,
  selectedKey,
  onSelect,
  timeRange,
  windowLabel,
  renderExpanded,
  logLine,
}: Props) {
  const { t, i18n } = useTranslation();
  const names = failedNames(t, feed);
  const summary = listSummary(t, i18n.language, tab, feed, timeRange);

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
            <RotateCw />
            {t("activity.failed.retry")}
          </Button>
        }
      />
    );
  }
  // Everything loaded so far is hidden by a client-side filter or the merge
  // frontier, and older records exist: keep reading rather than say "none".
  if (feed.rows.length === 0 && feed.hasOlder) return <LoadOlder feed={feed} />;
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
      <div className="border-t border-border-subtle">
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
      </div>
    );
  }
  return (
    <>
      {logLine}
      <ActivityList
        tab={tab}
        rows={feed.rows}
        agents={agents}
        selectedKey={selectedKey}
        onSelect={onSelect}
        summary={summary}
        windowLabel={windowLabel}
        renderExpanded={renderExpanded}
      />
      <LoadOlder feed={feed} />
    </>
  );
}
