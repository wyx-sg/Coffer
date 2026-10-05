// src/components/mcp/server/CapabilityToolbar.tsx — the toolbar and bulk pieces of the Tools, Resources and Prompts tables (design 4.1.10–4.1.12).
//
// The toolbar is the search alone (the tab is named by the tab strip, so no
// title, and no count). Rows are
// switched on and off together by ticking them: the tables take a select-all
// box in the header and a box per row, and while any is ticked the selection
// bar (BulkOnOffActions inside a ListSelectionBar) replaces this toolbar.
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Checkbox } from "@/components/ui/checkbox";

/** What a table needs to draw its checkboxes: the ticked keys and how to change them. */
export interface CapabilitySelection {
  keys: ReadonlySet<string>;
  toggle: (key: string) => void;
  /** Every row the search matches (select-all reaches all of them, not only the rendered page). */
  allKeys: readonly string[];
  setMany: (keys: string[], on: boolean) => void;
  /** How many matching rows are ticked. */
  count: number;
}

/** The header's select-all box. */
export function SelectAllBox({ selection }: { selection: CapabilitySelection }) {
  const { t } = useTranslation();
  const all = selection.allKeys.length > 0 && selection.count === selection.allKeys.length;
  return (
    <Checkbox
      checked={all}
      indeterminate={selection.count > 0 && !all}
      aria-label={t("common.bulk.selectAll")}
      onChange={() => selection.setMany([...selection.allKeys], !all)}
    />
  );
}

/** A row's box; its clicks and keys never reach the row (which may open on them). */
export function RowSelectBox({
  selection,
  rowKey,
  name,
}: {
  selection: CapabilitySelection;
  rowKey: string;
  name: string;
}) {
  const { t } = useTranslation();
  return (
    <Checkbox
      checked={selection.keys.has(rowKey)}
      aria-label={t("agents.kindTab.selectRow", { name })}
      onChange={() => selection.toggle(rowKey)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    />
  );
}

interface Props {
  placeholder: string;
  query: string;
  onQueryChange: (query: string) => void;
}

export function CapabilityToolbar({ placeholder, query, onQueryChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <SearchInput
        value={query}
        onChange={onQueryChange}
        placeholder={placeholder}
        ariaLabel={placeholder}
        className="w-64"
      />
    </div>
  );
}
