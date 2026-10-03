// frontend/src/components/reach/ReachFilter.tsx
//
// The "Reach" filter of a scoped list: the three states ReachControl shows,
// under the same names (`lib/reachFilter.ts`), as a filter pill (nothing chosen
// = All). One control for the Skills library, the MCP servers list and the
// custom-tool groups, so the column, the filter and the button all ask the one
// question in one word.
import { useTranslation } from "react-i18next";

import { FilterPill } from "@/components/filters";
import { reachFilterOptions, type ReachFilterValue } from "@/lib/reachFilter";

interface Props {
  value: ReachFilterValue;
  onChange: (value: ReachFilterValue) => void;
}

export function ReachFilter({ value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <FilterPill
      mode="single"
      label={t("resources.cols.reach")}
      options={reachFilterOptions(t)}
      fixedOrder
      value={value === "all" ? null : value}
      onChange={(v) => onChange((v ?? "all") as ReachFilterValue)}
    />
  );
}
