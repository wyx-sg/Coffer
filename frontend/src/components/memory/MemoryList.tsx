// frontend/src/components/memory/MemoryList.tsx — a partition's memories, then its Retired group.
//
// The left column of the Memories tab (spec memory "Present a partition as its
// memories"): each memory as its title and one-line description, the selected
// one highlighted. Under them, a collapsed "Retired (n)" group, read-only:
// each retired memory with the reason it left. There is no Restore and no
// per-memory action anywhere — a memory is derived by distillation, and the
// list says so by offering none.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { NoteSummaryOut, RetiredNoteOut } from "@/lib/api/memoryTypes";
import { cn } from "@/lib/utils";

interface Props {
  memories: NoteSummaryOut[];
  retired: RetiredNoteOut[];
  selected: string | null;
  onSelect: (slug: string) => void;
}

export function MemoryList({ memories, retired, selected, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col">
      <ul aria-label={t("memory.memories.listLabel")} className="flex flex-col gap-0.5">
        {memories.map((m) => {
          const active = m.slug === selected;
          return (
            <li key={m.slug}>
              <button
                type="button"
                aria-current={active ? "true" : undefined}
                onClick={() => onSelect(m.slug)}
                className={cn(
                  "flex w-full flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left",
                  active ? "bg-surface-selected" : "hover:bg-surface-hover",
                )}
              >
                <span className="truncate text-sm font-label text-text">{m.title}</span>
                {m.description ? (
                  <span className="truncate text-xs text-text-muted">{m.description}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
      {retired.length > 0 ? <RetiredGroup retired={retired} /> : null}
    </div>
  );
}

function RetiredGroup({ retired }: { retired: RetiredNoteOut[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="mt-2.5 border-t border-border-subtle pt-2" data-testid="memory-retired">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-[30px] w-full items-center gap-1.5 rounded-md px-2.5 text-left text-xs font-semibold text-text-muted hover:bg-surface-hover"
      >
        <Chevron className="size-3.5" aria-hidden />
        {t("memory.memories.retired")}
        <span className="font-book">{retired.length}</span>
        <span className="ml-auto font-book">{t("memory.memories.readOnly")}</span>
      </button>
      {open ? (
        <ul className="mt-1 flex flex-col gap-0.5">
          {retired.map((r) => (
            <li key={r.slug} className="flex flex-col gap-0.5 px-2.5 py-1.5">
              <span className="truncate text-sm text-text-muted">{r.title}</span>
              {r.reason ? <span className="text-xs text-text-subtle">{r.reason}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
