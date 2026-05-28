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
import { TimeRangePicker } from "@/components/TimeRangePicker";

/** Actor options shown in the filter (besides "all"). */
export const ACTORS = ["ui", "cli", "api", "system"] as const;

export interface AuditFiltersState {
  /** Free-text query, matched client-side against each entry. */
  search: string;
  /** A TIME_PRESETS key, or "custom" when from/to are set. */
  timeRange: string;
  /** "YYYY-MM-DD HH:mm:ss" datetimes — used only when timeRange === "custom". */
  from: string;
  to: string;
  /** "all" or one of ACTORS — applied client-side. */
  actor: string;
}

interface Props {
  state: AuditFiltersState;
  onChange: (next: AuditFiltersState) => void;
}

/**
 * Audit log filters: a free-text search, a time range (presets + a custom
 * calendar/typed window), and an actor. Renders bare controls — the
 * caller wraps them in a card.
 */
export function AuditFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <div>
        <Label htmlFor="filter-search">{t("audit.filter.search")}</Label>
        <SearchInput
          id="filter-search"
          value={state.search}
          onChange={(v) => onChange({ ...state, search: v })}
          placeholder={t("audit.filter.searchPlaceholder")}
        />
      </div>
      <div>
        <Label>{t("audit.filter.time")}</Label>
        <TimeRangePicker
          timeRange={state.timeRange}
          from={state.from}
          to={state.to}
          onChange={(v) => onChange({ ...state, ...v })}
        />
      </div>
      <div>
        <Label htmlFor="filter-actor">{t("audit.filter.actor")}</Label>
        <Select value={state.actor} onValueChange={(v) => onChange({ ...state, actor: v })}>
          <SelectTrigger id="filter-actor">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("audit.filter.all")}</SelectItem>
            {ACTORS.map((a) => (
              <SelectItem key={a} value={a}>
                {t(`audit.actor.${a}`, { defaultValue: a })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
