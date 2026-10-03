// src/components/ListSelectAll.tsx — the select-all box of a list that has no table header.
//
// Lists (MCP servers, Skills) have no header row, so the one that tables put at
// the top of the checkbox column appears as a slim row under the selection bar
// once something is ticked: "Select all", indeterminate when only some listed
// rows are ticked (Foundations 0.6.02; the bulk bar itself has no select-all).
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";

interface Props {
  /** How many of the listed (filtered) rows are ticked, and how many are listed. */
  count: number;
  total: number;
  onChange: (all: boolean) => void;
}

export function ListSelectAll({ count, total, onChange }: Props) {
  const { t } = useTranslation();
  if (count === 0 || total === 0) return null;
  const all = count >= total;
  return (
    <label className="flex h-7 cursor-pointer items-center gap-2.5 px-2.5 text-2xs font-semibold text-text-muted">
      <Checkbox
        checked={all}
        indeterminate={!all}
        aria-label={t("common.bulk.selectAll")}
        onChange={() => onChange(!all)}
      />
      {t("common.bulk.selectAll")}
    </label>
  );
}
