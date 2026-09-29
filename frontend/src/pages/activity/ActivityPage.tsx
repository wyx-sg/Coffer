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
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ActivityBody, NewRecordsStrip, PartialFailure } from "@/components/activity/ActivityBody";
import { ActivityFilterBar } from "@/components/activity/ActivityFilterBar";
import { ActivityHeader } from "@/components/activity/ActivityHeader";
import { RecordDrawer } from "@/components/activity/RecordDrawer";
import { DEFAULT_FILTERS, filtersNarrow, type ActivityFilters } from "@/lib/activity/filters";
import { ACTIVITY_TABS, type ActivityTab } from "@/lib/activity/records";
import { useActivityFeed } from "@/lib/hooks/useActivityFeed";
import { useActivityLookups } from "@/lib/hooks/useActivityLookups";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";

function isActivityTab(value: string | null): value is ActivityTab {
  return (ACTIVITY_TABS as readonly string[]).includes(value ?? "");
}

/** Within this many pixels of the top counts as "at the top". */
const TOP_SLACK = 8;

export function ActivityPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: ActivityTab = isActivityTab(requested) ? requested : "everything";
  const [filters, setFilters] = useState<ActivityFilters>(DEFAULT_FILTERS);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [atTop, setAtTop] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    if (next === "everything") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
    setSelectedKey(null);
  };

  const lookups = useActivityLookups();
  const feed = useActivityFeed({
    tab,
    filters,
    t,
    agentNames: lookups.agentNames,
    serverNames: lookups.serverNames,
  });

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
  const { hasPending, releaseAll } = feed;
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

  // Clearing keeps the time window: it is the page's frame, not a filter.
  const clearFilters = () =>
    setFilters({
      ...DEFAULT_FILTERS,
      timeRange: filters.timeRange,
      from: filters.from,
      to: filters.to,
    });

  return (
    // Full-bleed, like Conversations: the list and the drawer each own a
    // scroll region, so "at the top" is the list's own scroll position.
    <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-col gap-3.5 px-6 pt-6 md:px-8">
          <ActivityHeader
            tab={tab}
            onTab={setTab}
            counts={feed.counts}
            live={streamOpen}
            specs={feed.specs}
            keep={feed.keep}
          />
          <ActivityFilterBar
            tab={tab}
            filters={filters}
            onChange={setFilters}
            agents={lookups.agents}
            servers={lookups.servers}
            loggers={feed.loggers}
          />
          <PartialFailure feed={feed} />
          <NewRecordsStrip held={!live} feed={feed} onShowNew={showNew} />
        </div>
        <div
          ref={scrollRef}
          onScroll={onScroll}
          data-activity-list
          className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 md:px-5"
        >
          <ActivityBody
            tab={tab}
            feed={feed}
            narrowed={filtersNarrow(filters, tab)}
            onClearFilters={clearFilters}
            agents={lookups.agentLooks}
            selectedKey={selected?.key ?? null}
            onSelect={setSelectedKey}
          />
        </div>
      </div>
      {selected ? (
        <div className="absolute inset-0 z-10 flex md:static md:z-auto">
          <RecordDrawer
            record={selected}
            rows={feed.rows}
            agents={lookups.agentLooks}
            onSelect={setSelectedKey}
            onClose={() => setSelectedKey(null)}
          />
        </div>
      ) : null}
    </div>
  );
}
