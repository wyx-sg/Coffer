// frontend/src/components/DataTableToolbar.tsx
// The search box + dropdown filters row for DataTable, extracted so the table
// component stays within its size budget. Purely presentational: it owns no
// state — the parent passes the current values and gets change callbacks (and
// resets pagination on change).
import { SearchInput } from "@/components/SearchInput";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
        <Select
          key={f.key}
          value={filterVals[f.key] ?? "all"}
          onValueChange={(v) => onFilterChange(f.key, v)}
        >
          <SelectTrigger aria-label={f.label} className="h-9 w-auto min-w-[8rem]">
            <SelectValue placeholder={f.label} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{f.allLabel}</SelectItem>
            {f.options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}
    </div>
  );
}
