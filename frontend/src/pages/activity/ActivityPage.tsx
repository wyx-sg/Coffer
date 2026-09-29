// src/pages/activity/ActivityPage.tsx — what just happened, and why did it fail: Coffer's three records on one page.
//
// Four tabs (spec web-ui "Gather the three records on one Activity page"):
// Everything merges the audit log, the MCP calls the gateway proxied and the
// daemon's warnings and errors into one newest-first stream; Changes, MCP
// calls and Daemon log narrow to one record each, with the columns and
// filters that record affords. Each tab shows its count.
//
// Live without a control (spec web-ui "Stream new Activity records while the
// list is at the top"): new records stream in at the top while the reader is
// at the top with nothing open; once they scroll down or open a record,
// insertion stops and "↑ N new" counts what is waiting. Choosing it — or
// scrolling back to the top — inserts them. There is no Pause / Resume and no
// refresh button; the ⋯ menu exports the filtered records.
//
// The tab lives in the URL (`?tab=`, Everything by default), so a link can
// land on the daemon log and a reload comes back where it was.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowUp, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/status/StatusDot";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { translateApiError } from "@/lib/api/errors";
import {
  ACTIVITY_TABS,
  DEFAULT_FILTERS,
  filtersNarrow,
  type ActivityFilters,
  type ActivityTab,
} from "@/lib/activity/records";
import { useActivityFeed, type TabCount } from "@/lib/hooks/useActivityFeed";
import { useAgents } from "@/lib/hooks/useAgents";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useResources } from "@/lib/hooks/useResources";
import { cn } from "@/lib/utils";
import { ActivityFilterBar, type AgentOption, type ServerOption } from "./ActivityFilterBar";
import { ActivityList } from "./ActivityList";
import { ActivityMenu } from "./ActivityMenu";
import { RecordDrawer } from "./RecordDrawer";
import type { AgentLook } from "./activityCells";

function isActivityTab(value: string | null): value is ActivityTab {
  return (ACTIVITY_TABS as readonly string[]).includes(value ?? "");
}

/** Within this many pixels of the top counts as "at the top". */
const TOP_SLACK = 8;

function CountBadge({ count }: { count: TabCount }) {
  const { i18n, t } = useTranslation();
  if (count.value === undefined) return null;
  const n = count.value.toLocaleString(i18n.language);
  return (
    <span data-visual-volatile className="text-2xs font-book text-text-subtle">
      {count.floor ? t("activity.countFloor", { value: n }) : n}
    </span>
  );
}

export function ActivityPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: ActivityTab = isActivityTab(requested) ? requested : "everything";
  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    if (next === "everything") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
    setSelectedKey(null);
  };

  const [filters, setFilters] = useState<ActivityFilters>(DEFAULT_FILTERS);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [atTop, setAtTop] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const agentsQuery = useAgents();
  const serversQuery = useResources("mcp_server");
  const agentOptions: AgentOption[] = useMemo(
    () => (agentsQuery.data ?? []).map((a) => ({ uid: a.uid, type: a.type, name: a.display_name })),
    [agentsQuery.data],
  );
  const agentLooks = useMemo(
    () =>
      new Map<string, AgentLook>(agentOptions.map((a) => [a.uid, { type: a.type, name: a.name }])),
    [agentOptions],
  );
  const agentNames = useMemo(
    () => new Map(agentOptions.map((a) => [a.uid, a.name])),
    [agentOptions],
  );
  const serverOptions: ServerOption[] = useMemo(
    () => (serversQuery.data ?? []).map((s) => ({ uid: s.uid, label: s.title || s.name })),
    [serversQuery.data],
  );
  const serverNames = useMemo(
    () => new Map((serversQuery.data ?? []).map((s) => [s.uid, s.name])),
    [serversQuery.data],
  );

  const feed = useActivityFeed({ tab, filters, t, agentNames, serverNames });

  // A change the daemon announces also wrote an audit entry: read the audit
  // log's head now rather than at the next poll.
  const { refreshChanges } = feed;
  const { live: streamOpen } = useDaemonEvents({
    onMessage: (message) => {
      if (message.type === "change") refreshChanges();
    },
  });

  const selected = feed.rows.find((r) => r.key === selectedKey) ?? null;
  const live = atTop && selected === null;

  // Live: whatever arrived is inserted at once. Held: it waits for the pill.
  const { pendingCount, hasPending, releaseAll } = feed;
  useEffect(() => {
    if (live && hasPending) releaseAll();
  }, [live, hasPending, releaseAll]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el) setAtTop(el.scrollTop <= TOP_SLACK);
  }, []);

  const showNew = () => {
    releaseAll();
    scrollRef.current?.scrollTo({ top: 0 });
    setAtTop(true);
  };

  const narrowed = filtersNarrow(filters, tab);
  const failedNames = feed.failed.map((s) => t(`activity.sources.${s.source}`));
  const allFailed =
    feed.failed.length > 0 && feed.failed.length === (tab === "everything" ? feed.specs.length : 1);

  let body;
  if (feed.isLoading) {
    body = (
      <div className="flex flex-col gap-2 px-3 pt-3" aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    );
  } else if (allFailed) {
    body = (
      <EmptyState
        tone="error"
        icon={AlertCircle}
        title={t("activity.failed.title", { sources: failedNames.join(", ") })}
        description={translateApiError(t, feed.failed[0].error)}
        action={
          <Button variant="outline" onClick={() => feed.failed.forEach((s) => s.retry())}>
            {t("activity.failed.retry")}
          </Button>
        }
      />
    );
  } else if (feed.rows.length === 0) {
    body = narrowed ? (
      <EmptyState
        icon={ScrollText}
        title={t("activity.empty.noMatch")}
        description={t("activity.empty.noMatchBody")}
        action={
          <Button
            variant="outline"
            onClick={() =>
              setFilters({
                ...DEFAULT_FILTERS,
                timeRange: filters.timeRange,
                from: filters.from,
                to: filters.to,
              })
            }
          >
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
  } else {
    body = (
      <>
        <ActivityList
          tab={tab}
          rows={feed.rows}
          agents={agentLooks}
          selectedKey={selected?.key ?? null}
          onSelect={setSelectedKey}
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

  return (
    <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-col gap-3.5 px-6 pt-6 md:px-8">
          <PageHeader
            icon={ScrollText}
            title={t("activity.title")}
            subtitle={t("activity.subtitle")}
            badges={
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    role="img"
                    aria-label={streamOpen ? t("activity.live") : t("activity.notLive")}
                    className="inline-flex p-1"
                  >
                    <StatusDot tone={streamOpen ? "ok" : "off"} />
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {streamOpen ? t("activity.liveHint") : t("activity.notLiveHint")}
                </TooltipContent>
              </Tooltip>
            }
            actions={<ActivityMenu tab={tab} specs={feed.specs} keep={feed.keep} />}
          />

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              {ACTIVITY_TABS.map((value) => (
                <TabsTrigger key={value} value={value}>
                  {t(`activity.tabs.${value}`)}
                  <CountBadge count={feed.counts[value]} />
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <ActivityFilterBar
            tab={tab}
            filters={filters}
            onChange={setFilters}
            agents={agentOptions}
            servers={serverOptions}
            loggers={feed.loggers}
          />

          {feed.failed.length > 0 && !allFailed ? (
            <Alert variant="error">
              <AlertCircle />
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>
                  <span className="font-label text-text">
                    {t("activity.failed.title", { sources: failedNames.join(", ") })}
                  </span>{" "}
                  {t("activity.failed.partial")}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => feed.failed.forEach((s) => s.retry())}
                >
                  {t("activity.failed.retry")}
                </Button>
              </div>
            </Alert>
          ) : null}

          <div className="flex h-5 items-center justify-center text-2xs text-text-subtle">
            {!live && pendingCount > 0 ? (
              <button
                type="button"
                onClick={showNew}
                className="inline-flex h-6 items-center gap-1 rounded-full bg-accent px-2.5 text-xs font-semibold text-accent-foreground shadow-overlay"
              >
                <ArrowUp className="size-3" aria-hidden />
                {t("activity.pending", { count: pendingCount })}
              </button>
            ) : (
              <span data-visual-volatile className="ml-auto">
                {feed.loaded > 0 ? t("activity.loaded", { count: feed.loaded }) : null}
              </span>
            )}
          </div>
        </div>

        <div
          ref={scrollRef}
          onScroll={onScroll}
          data-activity-list
          className={cn("min-h-0 flex-1 overflow-y-auto px-3 pb-6 md:px-5")}
        >
          {body}
        </div>
      </div>

      {selected ? (
        <div className="absolute inset-0 z-10 flex md:static md:z-auto">
          <RecordDrawer
            record={selected}
            rows={feed.rows}
            agents={agentLooks}
            onSelect={setSelectedKey}
            onClose={() => setSelectedKey(null)}
          />
        </div>
      ) : null}
    </div>
  );
}
