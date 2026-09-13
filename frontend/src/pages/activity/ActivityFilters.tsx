// frontend/src/pages/activity/ActivityFilters.tsx
//
// The half of the filter bar every Activity tab has — free text and a time
// window — with a slot for the one control that tab adds (an actor select on
// Changes, an errors-only switch on Daemon). The MCP calls tab brings its own
// bar (InvocationsFilters) because that table is shared with the MCP server
// detail page.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { SearchInput } from "@/components/SearchInput";
import { TimeRangePicker } from "@/components/TimeRangePicker";

/** What every Activity tab's filter state has in common. */
export interface ActivityFilterState {
  /** Free-text query, matched client-side against each row's haystack. */
  search: string;
  /** A TIME_PRESETS key, or "custom" when from/to are set. */
  timeRange: string;
  /** "YYYY-MM-DD HH:mm:ss" datetimes — used only when timeRange === "custom". */
  from: string;
  to: string;
}

interface Props<T extends ActivityFilterState> {
  state: T;
  onChange: (next: T) => void;
  searchPlaceholder: string;
  /** The tab's own extra control, rendered after the time range. */
  children?: ReactNode;
}

/**
 * Laid out as the same inline toolbar the shared DataTable renders
 * (SearchInput + h-9 controls, no labels, no card) so every Activity tab
 * matches the other list surfaces.
 */
export function ActivityFilters<T extends ActivityFilterState>({
  state,
  onChange,
  searchPlaceholder,
  children,
}: Props<T>) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={state.search}
        onChange={(v) => onChange({ ...state, search: v })}
        placeholder={searchPlaceholder}
        ariaLabel={t("audit.filter.search")}
        className="w-full sm:max-w-xs"
      />
      <TimeRangePicker
        timeRange={state.timeRange}
        from={state.from}
        to={state.to}
        onChange={(v) => onChange({ ...state, ...v })}
      />
      {children}
    </div>
  );
}
