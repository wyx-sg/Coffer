// frontend/src/components/reach/ReachFilter.tsx
//
// The "Reach" filter of a scoped list: All, then the three states ReachControl
// shows, under the same names (`lib/reachFilter.ts`). One control for the
// Skills library, the MCP servers list and the custom-tool groups, so the
// column, the filter and the button all ask the one question in one word.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { reachFilterOptions, type ReachFilterValue } from "@/lib/reachFilter";

interface Props {
  value: ReachFilterValue;
  onChange: (value: ReachFilterValue) => void;
  /** Sits beside a search field: no visible label; the trigger reads
   *  "Reach: All" itself, and the name stays as its aria-label and tooltip. */
  compact?: boolean;
}

export function ReachFilter({ value, onChange, compact = false }: Props) {
  const { t } = useTranslation();
  const label = t("resources.cols.reach");
  const optionLabel =
    value === "all"
      ? t("resources.status.all")
      : (reachFilterOptions(t).find((o) => o.value === value)?.label ?? value);
  return (
    <div className="flex items-center gap-2">
      {compact ? null : (
        <span className="text-xs font-semibold text-text-muted" aria-hidden>
          {label}
        </span>
      )}
      <Select value={value} onValueChange={(v) => onChange(v as ReachFilterValue)}>
        <SelectTrigger
          aria-label={label}
          title={compact ? label : undefined}
          className="h-control-sm w-auto text-xs"
        >
          {compact ? <SelectValue>{`${label}: ${optionLabel}`}</SelectValue> : <SelectValue />}
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("resources.status.all")}</SelectItem>
          {reachFilterOptions(t).map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
