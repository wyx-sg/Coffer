// frontend/src/components/DataTableToolbar.tsx
// The search box + filter pills row for DataTable, extracted so the table
// component stays within its size budget. Purely presentational: it owns no
// state — the parent passes the current values and gets change callbacks (and
// resets pagination on change).
import { SearchInput } from "@/components/SearchInput";
import { FilterPill } from "@/components/filters";
import type { FilterDef } from "@/components/DataTable";

interface Props<T> {
  query: string;
  onQueryChange: (v: string) => void;
  searchPlaceholder?: string;
  filters: FilterDef<T>[];
  filterVals: Record<string, string>;
  onFilterChange: (key: string, v: string) => void;
}

export function DataTableToolbar<T>({
  query,
  onQueryChange,
  searchPlaceholder,
  filters,
  filterVals,
  onFilterChange,
}: Props<T>) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {searchPlaceholder !== undefined ? (
        <SearchInput
          value={query}
          onChange={onQueryChange}
          placeholder={searchPlaceholder}
          ariaLabel={searchPlaceholder}
          className="w-full sm:max-w-xs"
        />
      ) : null}
      {filters.map((f) => (
        <FilterPill
          key={f.key}
          mode="single"
          label={f.label}
          options={f.options}
          value={filterVals[f.key] && filterVals[f.key] !== "all" ? filterVals[f.key] : null}
          onChange={(v) => onFilterChange(f.key, v ?? "all")}
        />
      ))}
    </div>
  );
}
