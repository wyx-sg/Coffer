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
// A record opens in a drawer beside the list; on the Daemon log it expands in
// place under its own line instead (design 6.1.09).
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ActivityBody } from "@/components/activity/ActivityBody";
import { ActivityFilterBar } from "@/components/activity/ActivityFilterBar";
import { ActivityHeader } from "@/components/activity/ActivityHeader";
import { NewRecordsStrip, PartialFailure } from "@/components/activity/ActivityNotices";
import { useTimeRangeLabel } from "@/components/activity/ActivityTimeRange";
import { DaemonLogLine, DaemonRecordOpen, OpenLogFile } from "@/components/activity/DaemonLogParts";
import { RecordDrawer } from "@/components/activity/RecordDrawer";
import { filtersNarrow } from "@/lib/activity/filters";
import { useActivityFeed } from "@/lib/hooks/useActivityFeed";
import { useActivityLookups } from "@/lib/hooks/useActivityLookups";
import { useActivityView } from "@/lib/hooks/useActivityView";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";

/** Within this many pixels of the top counts as "at the top". */
const TOP_SLACK = 8;

export function ActivityPage() {
  const { t } = useTranslation();
  const view = useActivityView();
  const { tab, filters, setTab } = view;
  const [atTop, setAtTop] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const lookups = useActivityLookups();
  const feed = useActivityFeed({
    tab,
    filters,
    t,
    agentNames: lookups.agentNames,
    serverNames: lookups.serverNames,
  });
  const windowLabel = useTimeRangeLabel(filters);

  // A change the daemon announces also wrote an audit entry: read the audit
  // log's head now rather than at the next poll.
  const { refreshChanges } = feed;
  const { live: streamOpen } = useDaemonEvents({
    onMessage: (message) => {
      if (message.type === "change") refreshChanges();
    },
  });

  const selected = feed.rows.find((r) => r.key === view.selectedKey) ?? null;
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
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setAtTop(true);
  };

  const daemon = tab === "daemon";
  return (
    // Full-bleed, like Conversations: the list and the drawer each own a
    // scroll region, so "at the top" is the list's own scroll position.
    <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-col gap-3.5 px-6 pt-6 md:px-8">
          <ActivityHeader
            tab={tab}
            onTab={(next) => setTab(next)}
            counts={feed.counts}
            live={streamOpen}
            specs={feed.specs}
            keep={feed.keep}
          />
          <ActivityFilterBar
            tab={tab}
            filters={filters}
            onChange={view.changeFilters}
            agents={lookups.agents}
            agentNames={lookups.agentNames}
            servers={lookups.servers}
            loggers={feed.loggers}
            loaded={feed.loadedRecords}
            counts={feed.counts}
            trailing={daemon ? <OpenLogFile path={feed.logPath} /> : null}
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
            onClearFilters={view.clearFilters}
            agents={lookups.agentLooks}
            selectedKey={selected?.key ?? null}
            onSelect={view.select}
            timeRange={filters.timeRange}
            windowLabel={windowLabel}
            logLine={
              daemon && feed.logPath ? (
                <DaemonLogLine path={feed.logPath} following={streamOpen && live} />
              ) : null
            }
            renderExpanded={
              daemon
                ? (r) => (
                    <DaemonRecordOpen
                      record={r}
                      onShowCall={(search) => setTab("mcp", { search })}
                    />
                  )
                : undefined
            }
          />
        </div>
      </div>
      {selected && !daemon ? (
        <div className="absolute inset-0 z-10 flex md:static md:z-auto">
          <RecordDrawer
            record={selected}
            rows={feed.rows}
            agents={lookups.agentLooks}
            transports={lookups.serverTransports}
            onSelect={view.setSelectedKey}
            onClose={() => view.setSelectedKey(null)}
            onDaemonRecords={(server) => setTab("daemon", { search: server })}
          />
        </div>
      ) : null}
    </div>
  );
}
