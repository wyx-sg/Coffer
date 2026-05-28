// frontend/src/kinds/mcp/InvocationsFilters.tsx
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
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
 * Invocations filter bar: free-text search, time range picker, and status
 * filter. Mirrors the AuditFilters layout (label-above-control, 3-column grid).
 */
export function InvocationsFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  function handleTimeRange(v: TimeRangeValue) {
    onChange({ ...state, timeRange: v.timeRange, from: v.from, to: v.to });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <div>
        <Label htmlFor="inv-filter-search">{t("mcp.invocations.filterSearch")}</Label>
        <SearchInput
          id="inv-filter-search"
          value={state.search}
          onChange={(v) => onChange({ ...state, search: v })}
          placeholder={t("mcp.invocations.searchPlaceholder")}
        />
      </div>
      <div>
        <Label>{t("mcp.invocations.filterTime")}</Label>
        <TimeRangePicker
          timeRange={state.timeRange}
          from={state.from}
          to={state.to}
          onChange={handleTimeRange}
        />
      </div>
      <div>
        <Label htmlFor="inv-filter-status">{t("mcp.invocations.filterStatus")}</Label>
        <Select
          value={state.status}
          onValueChange={(v) => onChange({ ...state, status: v as InvocationStatusFilter | "all" })}
        >
          <SelectTrigger id="inv-filter-status" aria-label={t("mcp.invocations.filterStatus")}>
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
    </div>
  );
}
