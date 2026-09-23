// frontend/src/pages/activity/DaemonTab.tsx
//
// The Daemon tab: the daemon's own log — the only one of the three records
// that carries what broke. Its own table, its own columns: a log record has a
// level and a logger, which neither of the other two records has.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DataTable } from "@/components/DataTable";
import { RawLog } from "@/components/RawLog";
import { useDaemonLog } from "@/lib/hooks/useDaemonLog";
import { translateApiError } from "@/lib/api/errors";
import { resolveTimeWindow } from "@/lib/timeRange";
import { ActivityFilters, type ActivityFilterState } from "./ActivityFilters";
import { daemonSearchHaystack } from "./activityText";
import { daemonColumns, type DaemonRow } from "./daemonColumns";
import type { components } from "@/lib/api/types";

type DaemonLogRecord = components["schemas"]["DaemonLogRecordOut"];

/** The daemon caps a log query at 500 lines of tail. */
/** Radix forbids an empty option value, so "every level" travels as a word
 *  here and becomes "" at the query. */
const ALL_LEVELS = "all";
const LEVEL_FLOORS = ["", "debug", "info", "warning", "error"] as const;

const LIMIT = 500;

interface DaemonFiltersState extends ActivityFilterState {
  /** Applied server-side — the route drops everything below error. */
  /** Severity floor; "" is every level. */
  level: string;
}

const DEFAULT_FILTERS: DaemonFiltersState = {
  search: "",
  timeRange: "all",
  from: "",
  to: "",
  level: "",
};

/**
 * Where an undated line gets its time from.
 *
 * The route returns the file's tail NEWEST-FIRST and keeps a line that was not
 * JSON rather than dropping it — almost always a traceback, written to the file
 * immediately AFTER the structlog record that raised it. Reversed, that means
 * the owning record sits at a HIGHER index than its traceback lines, so an
 * undated line borrows the timestamp of the nearest record after it: the exact
 * moment it was written, and a position directly beside the record it belongs
 * to. Failing that — a tail that opens mid-traceback — it borrows backwards.
 *
 * A line with nothing to borrow from at all keeps null, and its row renders a
 * dash: printing `1970-01-01` would claim a time the record does not have.
 */
function borrowedTimestamp(records: DaemonLogRecord[], index: number): string | null {
  for (let i = index + 1; i < records.length; i += 1) {
    if (records[i].timestamp) return records[i].timestamp as string;
  }
  for (let i = index - 1; i >= 0; i -= 1) {
    if (records[i].timestamp) return records[i].timestamp as string;
  }
  return null;
}

/**
 * An ISO stamp as milliseconds. The daemon's own log writes `…Z` while the
 * custom range's upper bound comes from the browser as `…000Z`; parsing both
 * removes a whole class of lexical-compare question.
 */
function timeMs(at: string): number {
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? 0 : ms;
}

interface Props {
  /** False while another tab is in front: no request, no discarded response. */
  enabled: boolean;
}

export function DaemonTab({ enabled }: Props) {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<DaemonFiltersState>(DEFAULT_FILTERS);

  // Memoise the window: resolveTimeWindow uses Date.now() for rolling presets,
  // so computing it inline would mint a fresh `since` every render — and
  // `since` is in the useDaemonLog queryKey, so that would refetch the log on
  // every keystroke. Recompute only when the time filter changes.
  const { timeRange, from, to, level } = filters;
  const { since, until } = useMemo(
    () => resolveTimeWindow({ timeRange, from, to }),
    [timeRange, from, to],
  );

  const { data, isLoading, error } = useDaemonLog({ since, level, limit: LIMIT, enabled });

  // The route applies `since` and the `level` floor server-side and returns the
  // tail newest-first; the custom-range upper bound and the free-text search
  // run client-side. No re-sort — DataTable preserves the order it is handed,
  // and an undated line is meant to stay beside the record it borrowed from.
  const records = data?.records;
  const { search } = filters;
  const rows = useMemo<DaemonRow[]>(() => {
    const all = records ?? [];
    let r: DaemonRow[] = all.map((rec, i) => ({
      id: String(i),
      rec,
      at: rec.timestamp || borrowedTimestamp(all, i),
    }));
    // A row with no time at all cannot be outside a window it never claimed to
    // be inside, so the upper bound leaves it alone.
    if (until) r = r.filter((row) => row.at === null || timeMs(row.at) <= timeMs(until));
    const query = search.trim().toLowerCase();
    if (query) r = r.filter((row) => daemonSearchHaystack(t, row.rec).includes(query));
    return r;
  }, [records, until, search, t]);

  return (
    <div className="space-y-4">
      <ActivityFilters
        state={filters}
        onChange={setFilters}
        searchPlaceholder={t("activity.daemon.searchPlaceholder")}
      >
        {/* A floor, not a toggle. "Errors only" hid the level most worth
            noticing BEFORE something breaks — a warning — behind reading the
            whole file, and offered no way to quiet the info chatter without
            also hiding those warnings. */}
        <Select
          value={filters.level || ALL_LEVELS}
          onValueChange={(v) => setFilters({ ...filters, level: v === ALL_LEVELS ? "" : v })}
        >
          <SelectTrigger className="w-[11rem]" aria-label={t("activity.daemon.levelLabel")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEVEL_FLOORS.map((level) => (
              <SelectItem key={level || "all"} value={level || ALL_LEVELS}>
                {t(`activity.daemon.level.${level || "all"}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </ActivityFilters>

      {/* isLoading, not isPending: a disabled query stays "pending" forever,
          which would leave a tab that has never been opened stuck on skeleton
          rows the moment it is. An error renders here, inside this tab — an
          older daemon with no /daemon/logs route 404s, and that must not
          blank the two records it does still serve. */}
      {error ? (
        <Card className="paper-card border-destructive/40">
          <CardContent className="py-4 text-destructive">{translateApiError(t, error)}</CardContent>
        </Card>
      ) : (
        <DataTable
          rows={rows}
          columns={daemonColumns(t)}
          rowKey={(row) => row.id}
          isLoading={isLoading}
          getRowDetail={(row) => (
            <div className="px-4 py-3">
              {/* The parsed structlog line itself, not the envelope the route
                  wraps it in — a line that was not JSON arrives as {raw}. */}
              <RawLog record={row.rec.record} />
            </div>
          )}
          emptyMessage={t("activity.daemon.emptyState")}
        />
      )}
    </div>
  );
}
