// src/components/filters/FilterRow.tsx — the one filter row (Foundations 0.2.06): segmented · search · pills · Clear filters.
//
// A page chooses its pills; position, size and spacing never change. The row
// has no result counts (principle 9), and "Clear filters" appears only while a
// filter is active, pushed to the right end.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  /** A status Segmented (default All); sits first when present. */
  segmented?: ReactNode;
  search?: {
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
    /** Focus key; give it to the one search the page leads with. */
    shortcut?: string;
  };
  /** The page's FilterPill / TimeRangePill elements. */
  children?: ReactNode;
  /** True while any filter, or the search text, is set. */
  active: boolean;
  /** Reset every filter and the search. */
  onClear: () => void;
  /** A page action at the far right, after "Clear filters" (Usage's Export CSV). */
  trailing?: ReactNode;
  className?: string;
}

export function FilterRow({
  segmented,
  search,
  children,
  active,
  onClear,
  trailing,
  className,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex min-h-[30px] flex-wrap items-center gap-2", className)}>
      {segmented}
      {search ? (
        <SearchInput
          value={search.value}
          onChange={search.onChange}
          placeholder={search.placeholder}
          ariaLabel={search.placeholder}
          shortcut={search.shortcut}
          className="w-[240px]"
        />
      ) : null}
      {children}
      {active ? (
        <Button variant="link" size="sm" className="ml-auto" onClick={onClear}>
          {t("filters.clearAll")}
        </Button>
      ) : null}
      {trailing ? <div className={cn(!active && "ml-auto")}>{trailing}</div> : null}
    </div>
  );
}
