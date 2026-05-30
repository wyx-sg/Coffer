import { useTranslation } from "react-i18next";
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
 * Audit log filters — a free-text search, a time range (presets + a custom
 * window), and an actor. Laid out as the same inline toolbar the shared
 * DataTable renders (SearchInput + h-9 selects, no labels, no card) so the
 * audit log matches every other list surface.
 */
export function AuditFilters({ state, onChange }: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={state.search}
        onChange={(v) => onChange({ ...state, search: v })}
        placeholder={t("audit.filter.searchPlaceholder")}
        ariaLabel={t("audit.filter.search")}
        className="w-full sm:max-w-xs"
      />
      <TimeRangePicker
        timeRange={state.timeRange}
        from={state.from}
        to={state.to}
        onChange={(v) => onChange({ ...state, ...v })}
      />
      <Select value={state.actor} onValueChange={(v) => onChange({ ...state, actor: v })}>
        <SelectTrigger aria-label={t("audit.filter.actor")} className="h-9 w-auto min-w-[8rem]">
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
  );
}
