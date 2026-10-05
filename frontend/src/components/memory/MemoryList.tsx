// frontend/src/components/memory/MemoryList.tsx — a partition's memories, then its Retired group.
//
// The left column of the Memories tab (spec memory "Show a partition's memories read-only"): each memory as its title and one-line description, the selected
// one highlighted. Under them, a collapsed "Retired (n)" group, read-only:
// each retired memory with the reason it left. There is no Restore and no
// action in the list: the selected memory's Edit sits on the pane beside it. The Retired group is pinned under the list
// (board 5.2.06): the memories scroll above it.
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { NoteSummaryOut, RetiredNoteOut } from "@/lib/api/memoryTypes";
import { AgentSources } from "./partitionFacts";
import { useProgressiveRows } from "@/components/ui/useProgressiveRows";
import { cn } from "@/lib/utils";

interface Props {
  memories: NoteSummaryOut[];
  retired: RetiredNoteOut[];
  selected: string | null;
  onSelect: (slug: string) => void;
  /** The selected retired memory, by its index in `retired`; null when none. */
  selectedRetired?: number | null;
  onSelectRetired?: (index: number) => void;
  /** The agents the partition came from: a memory learned from all of them
   *  reads "All agents" instead of a row of badges. */
  sources?: readonly string[];
}

export function MemoryList({
  memories,
  retired,
  selected,
  onSelect,
  selectedRetired = null,
  onSelectRetired,
  sources = [],
}: Props) {
  const { t } = useTranslation();
  // The selection is chosen by slug on the page, over the full list; only what
  // is drawn is sliced, and always far enough to draw the selected memory.
  const selectedAt = memories.findIndex((m) => m.slug === selected);
  const progressive = useProgressiveRows(memories, { initial: Math.max(50, selectedAt + 1) });
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ul
        aria-label={t("memory.memories.listLabel")}
        className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto"
      >
        {progressive.visible.map((m) => {
          const active = m.slug === selected;
          return (
            <li key={m.slug}>
              <button
                type="button"
                aria-current={active ? "true" : undefined}
                onClick={() => onSelect(m.slug)}
                className={cn(
                  "flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left",
                  active ? "bg-surface-selected" : "hover:bg-surface-hover",
                )}
              >
                <span className="flex min-w-0 grow flex-col gap-0.5">
                  <span className="truncate text-sm font-label text-text">{m.title}</span>
                  {m.description ? (
                    <span className="truncate text-xs text-text-muted">{m.description}</span>
                  ) : null}
                </span>
                <span className="shrink-0 pt-0.5">
                  <AgentSources agents={m.agents ?? []} everyone={sources} />
                </span>
              </button>
            </li>
          );
        })}
        {progressive.sentinel ? <li aria-hidden>{progressive.sentinel}</li> : null}
      </ul>
      {retired.length > 0 ? (
        <RetiredGroup retired={retired} selected={selectedRetired} onSelect={onSelectRetired} />
      ) : null}
    </div>
  );
}

/** The Retired group. With `onSelect` each record is a button that opens its
 *  read-only view beside the list; without it (no split view) the records read
 *  in full, titles and reasons untruncated. A selected record opens the group. */
export function RetiredGroup({
  retired,
  selected = null,
  onSelect,
}: {
  retired: RetiredNoteOut[];
  selected?: number | null;
  onSelect?: (index: number) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(selected !== null);
  const progressive = useProgressiveRows(retired, { initial: Math.max(50, (selected ?? -1) + 1) });
  useEffect(() => {
    if (selected !== null) setOpen(true);
  }, [selected]);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div
      className="mt-2.5 flex min-h-0 shrink-0 flex-col border-t border-border-subtle pt-2"
      data-testid="memory-retired"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-[30px] w-full shrink-0 items-center gap-1.5 rounded-md px-2.5 text-left text-xs font-semibold text-text-muted hover:bg-surface-hover"
      >
        <Chevron className="size-3.5" aria-hidden />
        {t("memory.memories.retired")}
        <span className="font-book">{retired.length}</span>
        <span className="ml-auto font-book">{t("memory.memories.readOnly")}</span>
      </button>
      {open ? (
        <ul
          aria-label={t("memory.memories.retiredListLabel")}
          className="mt-1 flex max-h-64 flex-col gap-0.5 overflow-y-auto"
        >
          {progressive.visible.map((r, i) => {
            const active = i === selected;
            const row = (
              <>
                <span
                  className={cn("text-sm text-text-muted", onSelect ? "truncate" : "break-words")}
                >
                  {r.title}
                </span>
                {r.reason ? (
                  <span
                    className={cn(
                      "text-xs text-text-subtle",
                      onSelect ? "truncate" : "break-words",
                    )}
                  >
                    {r.reason}
                  </span>
                ) : null}
              </>
            );
            return (
              <li key={`${r.slug}:${i}`}>
                {onSelect ? (
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    onClick={() => onSelect(i)}
                    className={cn(
                      "flex w-full flex-col gap-0.5 rounded-lg px-2.5 py-1.5 text-left",
                      active ? "bg-surface-selected" : "hover:bg-surface-hover",
                    )}
                  >
                    {row}
                  </button>
                ) : (
                  <div className="flex flex-col gap-0.5 px-2.5 py-1.5">{row}</div>
                )}
              </li>
            );
          })}
          {progressive.sentinel ? <li aria-hidden>{progressive.sentinel}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
