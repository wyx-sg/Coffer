// frontend/src/components/history/VersionHistorySplit.tsx
//
// The one layout every History tab shares (canvas 4.3.19, 4.3.20, boards 5.1.05
// onward): a bordered card split by a draggable divider — on the left the
// versions, newest first, under a "Versions" header with their count, each row
// an icon, a title (the newest wearing a Current chip), a muted line and,
// optionally, the lines it moved; on the right whatever the chosen version
// opens into (`detail`). The card fills the pane down to the bottom edge.
// The divider may be dragged down to a 160px list and up to leave the detail
// 320px — narrower bounds than a page-level split, so it moves both ways from
// its default (a list that opens at 250px has 90px to give, not 10).
import type { ReactNode } from "react";

import { useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { cn } from "@/lib/utils";

/** What one row of the version list shows. */
interface VersionRow {
  /** The leading mark (a tile or a badge). */
  icon: ReactNode;
  title: ReactNode;
  /** The muted line under the title. */
  subline: ReactNode;
  /** Right-aligned, e.g. the +N −M of this version. */
  trailing?: ReactNode;
}

interface Props<T> {
  /** Versions, newest first. */
  versions: readonly T[];
  getKey: (version: T) => string;
  selectedIndex: number;
  onSelect: (index: number) => void;
  renderRow: (version: T, index: number) => VersionRow;
  /** The list's header and accessible name ("Versions"). */
  listLabel: string;
  /** The chip on the newest version ("Current"). */
  currentLabel: string;
  /** The divider's accessible name. */
  dividerLabel: string;
  /** Names the remembered divider position (`coffer.split.<storageKey>`). */
  storageKey: string;
  /** The right pane: the chosen version's diffs. */
  detail: ReactNode;
  /** Mounted inside the card, beside the split (e.g. a restore dialog). */
  children?: ReactNode;
}

export function VersionHistorySplit<T>({
  versions,
  getKey,
  selectedIndex,
  onSelect,
  renderRow,
  listLabel,
  currentLabel,
  dividerLabel,
  storageKey,
  detail,
  children,
}: Props<T>) {
  const fill = useFillToBottom();

  const list = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border-subtle px-3">
        <span className="text-sm font-semibold text-text">{listLabel}</span>
        <span className="ml-auto text-xs text-text-subtle">{versions.length}</span>
      </div>
      <ul className="flex min-h-0 flex-1 flex-col gap-px overflow-auto p-1" aria-label={listLabel}>
        {versions.map((v, i) => {
          const active = i === selectedIndex;
          const row = renderRow(v, i);
          return (
            <li key={getKey(v)}>
              <button
                type="button"
                onClick={() => onSelect(i)}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-item p-2 text-left",
                  active ? "bg-surface-selected" : "hover:bg-surface-hover",
                )}
              >
                {row.icon}
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "min-w-0 truncate text-sm text-text",
                        active ? "font-label" : "font-medium",
                      )}
                    >
                      {row.title}
                    </span>
                    {i === 0 ? (
                      <span className="inline-flex h-[18px] shrink-0 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
                        {currentLabel}
                      </span>
                    ) : null}
                  </span>
                  <span className="truncate text-xs text-text-muted">{row.subline}</span>
                </span>
                {row.trailing ? (
                  <span className="shrink-0 whitespace-nowrap font-mono text-2xs text-text-subtle">
                    {row.trailing}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div
      ref={fill.ref}
      style={fill.style}
      className="flex min-h-0 overflow-hidden rounded-xl border border-border-subtle"
    >
      <SplitView
        storageKey={storageKey}
        label={dividerLabel}
        defaultListWidth={250}
        listMinWidth={160}
        detailMinWidth={320}
        className="min-h-0 flex-1"
        list={list}
        detail={detail}
      />
      {children}
    </div>
  );
}
