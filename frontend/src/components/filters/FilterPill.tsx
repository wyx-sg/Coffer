// src/components/filters/FilterPill.tsx — one filter as a pill ("Kind: MCP, Skill") that opens a checklist.
//
// Foundations 0.2.06: empty = the label and a chevron; chosen = "Label: value"
// with a × that clears. The popover is 232 wide, rows 28, no counts. A search
// box appears only above 8 values; the list shows six rows then scrolls;
// ordering is selected first, then A–Z. Multi keeps the popover open, single
// closes on pick. The footer is just "Clear".
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { FilterList } from "./FilterList";
import { buildSections } from "./filterSections";
import { PILL_BUTTON, pillClass } from "./pillStyles";

/** @ui-only One choice in a pill's list. */
export interface FilterOption {
  value: string;
  label: string;
  /** The `id` of a group in `groups` this row sits under. */
  group?: string;
}

/** @ui-only A heading over a run of options ("Agents" / "Not an agent"). */
export interface FilterGroup {
  id: string;
  label: string;
  /** Sort after the other groups (a "Not an agent" group). */
  last?: boolean;
}

interface BaseProps {
  /** The filter's name: "Kind". */
  label: string;
  options: readonly FilterOption[];
  groups?: readonly FilterGroup[];
  /** Placeholder for the search box ("Find a kind"); the box shows only above 8 values. */
  searchPlaceholder?: string;
  /** Keep `options` in the order given (small lists with a natural order). */
  fixedOrder?: boolean;
  className?: string;
}

interface MultiProps extends BaseProps {
  mode?: "multi";
  value: readonly string[];
  onChange: (value: string[]) => void;
}

interface SingleProps extends BaseProps {
  mode: "single";
  value: string | null;
  onChange: (value: string | null) => void;
}

export type FilterPillProps = MultiProps | SingleProps;

/** Search appears above this many values. */
const SEARCH_THRESHOLD = 8;
export function FilterPill(props: FilterPillProps) {
  const { label, options, groups, searchPlaceholder, fixedOrder, className } = props;
  const single = props.mode === "single";
  const selected = useMemo<string[]>(
    () => (props.mode === "single" ? (props.value ? [props.value] : []) : [...props.value]),
    [props.mode, props.value],
  );
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  // "Only" remembers the previous set so a second click restores it.
  const beforeOnly = useRef<string[] | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commit = (next: string[]) => {
    if (props.mode === "single") props.onChange(next[0] ?? null);
    else props.onChange(next);
  };

  const byValue = useMemo(() => new Map(options.map((o) => [o.value, o])), [options]);
  const valueText = selected.map((v) => byValue.get(v)?.label ?? v).join(", ");

  const searchable = options.length > SEARCH_THRESHOLD;
  const needle = query.trim().toLowerCase();
  const rows = useMemo(() => {
    const picked = new Set(selected);
    const collator = new Intl.Collator(i18n.language, { sensitivity: "base", numeric: true });
    let list = options.filter((o) => !needle || o.label.toLowerCase().includes(needle));
    if (!fixedOrder) {
      list = [...list].sort((a, b) => {
        const pa = picked.has(a.value) ? 0 : 1;
        const pb = picked.has(b.value) ? 0 : 1;
        return pa - pb || collator.compare(a.label, b.label);
      });
    }
    return list;
  }, [options, selected, needle, fixedOrder, i18n.language]);

  const sections = useMemo(() => buildSections(groups, rows), [groups, rows]);

  const toggle = (value: string) => {
    beforeOnly.current = null;
    if (single) {
      commit(selected[0] === value ? [] : [value]);
      setOpen(false);
      return;
    }
    commit(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  const only = (value: string) => {
    if (beforeOnly.current && selected.length === 1 && selected[0] === value) {
      commit(beforeOnly.current);
      beforeOnly.current = null;
    } else {
      beforeOnly.current = selected;
      commit([value]);
    }
  };

  const clear = () => {
    beforeOnly.current = null;
    commit([]);
  };

  const move = (e: KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = Array.from(
      listRef.current?.querySelectorAll<HTMLElement>("[role='option']") ?? [],
    );
    if (items.length === 0) return;
    e.preventDefault();
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? at + 1 : at - 1;
    items[(next + items.length) % items.length]?.focus();
  };

  const active = selected.length > 0;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <div className={cn(pillClass(active, open), className)}>
        <PopoverTrigger asChild>
          <button type="button" className={cn(PILL_BUTTON, active && "pr-1")}>
            <span className="shrink-0">{active ? `${label}:` : label}</span>
            {active ? (
              <span className="max-w-[220px] truncate font-[550] text-text">{valueText}</span>
            ) : null}
            {active ? null : <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />}
          </button>
        </PopoverTrigger>
        {active ? (
          <button
            type="button"
            onClick={clear}
            aria-label={t("filters.clearLabel", { label })}
            className="mr-1 grid size-4 shrink-0 place-items-center rounded-sm text-text-subtle hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <X className="size-3" aria-hidden />
          </button>
        ) : null}
      </div>
      <PopoverContent className="w-[232px] rounded-[10px] border border-border p-1" align="start">
        {searchable ? (
          <label className="mx-0.5 mb-1 mt-0.5 flex h-7 items-center gap-1.5 rounded-md border border-border bg-surface-raised px-2 text-xs text-text focus-within:ring-2 focus-within:ring-focus-ring">
            <Search className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={move}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder ?? label}
              className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-text-subtle"
            />
          </label>
        ) : null}
        <FilterList
          label={label}
          single={single}
          selected={selected}
          sections={sections}
          rowCount={rows.length}
          listRef={listRef}
          onKeyDown={move}
          onToggle={toggle}
          onOnly={only}
        />
        <div className="mt-1 border-t border-border-subtle pt-1">
          <button
            type="button"
            onClick={clear}
            disabled={!active}
            className="h-[30px] w-full rounded-sm px-2 text-left text-xs text-text-muted hover:bg-surface-hover hover:text-text disabled:pointer-events-none disabled:text-text-subtle disabled:opacity-disabled"
          >
            {t("filters.clear")}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
