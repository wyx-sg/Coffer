// src/components/filters/filterSections.ts — group a FilterPill's rows under their headings.
import type { FilterGroup, FilterOption } from "./FilterPill";

export interface FilterSection {
  id: string;
  label: string | undefined;
  rows: readonly FilterOption[];
}

/** Rows under their group headings; groups marked `last` sort after the rest. */
export function buildSections(
  groups: readonly FilterGroup[] | undefined,
  rows: readonly FilterOption[],
): FilterSection[] {
  if (!groups?.length) return [{ id: "", label: undefined, rows }];
  const ordered = [...groups.filter((g) => !g.last), ...groups.filter((g) => g.last)];
  const out = ordered
    .map((g) => ({
      id: g.id,
      label: g.label as string | undefined,
      rows: rows.filter((r) => r.group === g.id),
    }))
    .filter((s) => s.rows.length > 0);
  const known = new Set(groups.map((g) => g.id));
  const loose = rows.filter((r) => !r.group || !known.has(r.group));
  return loose.length ? [{ id: "", label: undefined, rows: loose }, ...out] : out;
}
