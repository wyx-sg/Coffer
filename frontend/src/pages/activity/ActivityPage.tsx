// src/pages/activity/ActivityPage.tsx — what just happened, and why did it fail: Coffer's three records on one page.
//
// Four tabs (spec web-ui "Gather the three records on one Activity page"):
// Everything merges the audit log, the MCP calls the gateway proxied and the
// daemon's warnings and errors into one newest-first stream; Changes, MCP
// calls and Daemon log narrow to one record each, with the columns and
// filters that record affords. Tabs carry no counts; one whose log failed to
// load shows a warning icon. Every filter lives in the URL.
//
// Everything opens small: each log the tab reads gives its newest 30 records,
// and the next 50 load when the list is scrolled to its end (or on "Load 50
// more"). Search and filters are asked of the logs themselves, never applied
// over what happens to be loaded.
//
// Live without a control (spec web-ui "Stream new Activity records while the
// list is at the top"): new records stream in at the top while the reader is
// at the top with nothing open; once they scroll down or open a record,
// insertion stops and "↑ N new" counts what is waiting. Choosing it — or
// scrolling back to the top — inserts them. There is no Pause / Resume and no
// refresh button; Export writes the filtered records.
//
// A record opens in the shared Drawer; on the Daemon log it expands in place
// under its own line instead (design 6.2.08). With no records at all the page
// is the first run: no filter row, no Export (design 6.2.09).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ActivityBody, FirstRun } from "@/components/activity/ActivityBody";
import { ActivityFilterBar } from "@/components/activity/ActivityFilterBar";
import { ActivityHeader } from "@/components/activity/ActivityHeader";
import { NewRecordsStrip, PartialFailure } from "@/components/activity/ActivityNotices";
import { DaemonRecordOpen } from "@/components/activity/DaemonLogParts";
import { RecordDrawer } from "@/components/activity/RecordDrawer";
import { filtersNarrow } from "@/lib/activity/filters";
import type { ActivityTab } from "@/lib/activity/records";
import { everyLogFailed } from "@/lib/activity/feedText";
import { useActivityAnyRecords } from "@/lib/hooks/useActivityAnyRecords";
import { useActivityFeed } from "@/lib/hooks/useActivityFeed";
import { useActivityLookups } from "@/lib/hooks/useActivityLookups";
import { useActivityView } from "@/lib/hooks/useActivityView";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";
import { useDebouncedValue } from "@/lib/hooks/useDebouncedValue";
import { useSortParam } from "@/lib/hooks/useSortParam";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

/** The tab each log belongs to, for the warning icon on a tab whose log failed. */
const SOURCE_TAB = { change: "changes", call: "mcp", daemon: "daemon" } as const;

/** Within this many pixels of the top counts as "at the top". */
const TOP_SLACK = 8;

export function ActivityPage() {
  const { t } = useTranslation();
  const view = useActivityView();
  const { tab, filters, setTab } = view;
  const [atTop, setAtTop] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const lookups = useActivityLookups();
  // The search box is the reader's immediately; the logs are asked once they
  // pause typing, and the request for the text before it is abandoned.
  const search = useDebouncedValue(filters.search);
  const feedFilters = useMemo(
    () => (search === filters.search ? filters : { ...filters, search }),
    [filters, search],
  );
  const feed = useActivityFeed({
    tab,
    filters: feedFilters,
    t,
    agentNames: lookups.agentNames,
  });
  const [sort, setSort] = useSortParam();

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
  const narrowed = filtersNarrow(filters, tab);
  const failedTabs = new Set<ActivityTab>(feed.failed.map((f) => SOURCE_TAB[f.source]));
  // Nothing under the default view: ask whether Coffer has recorded anything at all.
  const bare =
    !feed.isLoading &&
    !everyLogFailed(feed) &&
    feed.failed.length === 0 &&
    feed.rows.length === 0 &&
    !feed.hasOlder &&
    !narrowed;
  const firstRun = useActivityAnyRecords(bare) === false && bare;

  return (
    // Full-bleed, like Conversations: the list owns the scroll region, so
    // "at the top" is the list's own scroll position.
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "flex flex-col gap-4")}>
        <ActivityHeader
          tab={tab}
          onTab={(next) => setTab(next)}
          failedTabs={failedTabs}
          live={streamOpen}
        />
        {firstRun ? null : (
          <ActivityFilterBar
            tab={tab}
            filters={filters}
            onChange={view.changeFilters}
            onClear={view.clearFilters}
            agents={lookups.agents}
            loggers={feed.loggers}
          />
        )}
        <PartialFailure feed={feed} />
        <NewRecordsStrip held={!live} feed={feed} onShowNew={showNew} />
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        data-activity-list
        className="mt-3 min-h-0 flex-1 overflow-y-auto px-8 pb-10"
      >
        {firstRun ? (
          <FirstRun />
        ) : (
          <ActivityBody
            tab={tab}
            feed={feed}
            narrowed={narrowed}
            onClearFilters={view.clearFilters}
            agents={lookups.agentLooks}
            selectedKey={selected?.key ?? null}
            onSelect={view.select}
            sort={sort}
            onSort={setSort}
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
        )}
      </div>
      {selected && !daemon ? (
        <RecordDrawer
          record={selected}
          rows={feed.rows}
          agents={lookups.agentLooks}
          transports={lookups.serverTransports}
          onSelect={view.setSelectedKey}
          onClose={() => view.setSelectedKey(null)}
        />
      ) : null}
    </div>
  );
}
