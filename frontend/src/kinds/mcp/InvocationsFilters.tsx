// frontend/src/kinds/mcp/InvocationsFilters.tsx
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SearchInput } from "@/components/SearchInput";
import { TimeRangePicker, type TimeRangeValue } from "@/components/TimeRangePicker";
import type { InvocationStatusFilter } from "@/lib/hooks/useMcpInvocations";

export interface InvocationsFiltersState {
  search: string;
  timeRange: string;
  from: string;
  to: string;
  status: InvocationStatusFilter | "all";
}

interface Props {
  state: InvocationsFiltersState;
  onChange: (next: InvocationsFiltersState) => void;
}

/**
 * Invocations filter bar — free-text search, time range, and status. Laid out
 * as the same inline toolbar the shared DataTable renders (SearchInput + h-9
 * selects, no labels, no card) so it matches every other list surface.
 */
export function InvocationsFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  function handleTimeRange(v: TimeRangeValue) {
    onChange({ ...state, timeRange: v.timeRange, from: v.from, to: v.to });
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={state.search}
        onChange={(v) => onChange({ ...state, search: v })}
        placeholder={t("mcp.invocations.searchPlaceholder")}
        ariaLabel={t("mcp.invocations.filterSearch")}
        className="w-full sm:max-w-xs"
      />
      <TimeRangePicker
        timeRange={state.timeRange}
        from={state.from}
        to={state.to}
        onChange={handleTimeRange}
      />
      <Select
        value={state.status}
        onValueChange={(v) => onChange({ ...state, status: v as InvocationStatusFilter | "all" })}
      >
        <SelectTrigger
          aria-label={t("mcp.invocations.filterStatus")}
          className="h-9 w-auto min-w-[8rem]"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("audit.filter.all")}</SelectItem>
          <SelectItem value="ok">{t("mcp.invocations.status.ok")}</SelectItem>
          <SelectItem value="error">{t("mcp.invocations.status.error")}</SelectItem>
          <SelectItem value="timeout">{t("mcp.invocations.status.timeout")}</SelectItem>
          <SelectItem value="denied">{t("mcp.invocations.status.denied")}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
