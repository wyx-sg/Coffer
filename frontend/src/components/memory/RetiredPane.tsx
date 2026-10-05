// frontend/src/components/memory/RetiredPane.tsx — a retired memory, read-only.
//
// What the Retired group's record opens on the right of the Memories tab: the
// full title with a "Retired" tag, the date it was retired, the whole reason,
// and, when the memory that absorbed it is still in the list, a link to it.
// No Open in editor or Delete…: a retired memory is a record, not a note.
import { useTranslation } from "react-i18next";

import { FILE_PANE_SCROLL } from "@/components/filePane";
import type { NoteSummaryOut, RetiredNoteOut } from "@/lib/api/memoryTypes";
import { formatDateTime } from "@/lib/utils";

interface Props {
  record: RetiredNoteOut;
  memories: NoteSummaryOut[];
  onSelectMemory: (slug: string) => void;
}

export function RetiredPane({ record, memories, onSelectMemory }: Props) {
  const { t } = useTranslation();
  const replacement = record.replaced_by
    ? memories.find((m) => m.slug === record.replaced_by)
    : undefined;
  return (
    <article className="flex min-h-0 flex-1 flex-col gap-4" data-testid="retired-pane">
      <header className="flex flex-col gap-1.5">
        <div className="flex items-start gap-2">
          <h2 className="min-w-0 break-words text-md font-semibold text-text">{record.title}</h2>
          <span className="mt-0.5 shrink-0 rounded-md bg-surface-hover px-1.5 py-0.5 text-xs font-semibold text-text-muted">
            {t("memory.memories.retired")}
          </span>
        </div>
        <p className="text-xs text-text-muted">
          {t("memory.memories.retiredOn", { date: formatDateTime(record.retired_at) })}
        </p>
      </header>
      <div className={FILE_PANE_SCROLL}>
        <div className="flex max-w-[620px] flex-col gap-3 text-sm">
          {record.reason ? (
            <p className="whitespace-pre-wrap break-words text-text">{record.reason}</p>
          ) : null}
          {replacement ? (
            <button
              type="button"
              onClick={() => onSelectMemory(replacement.slug)}
              className="self-start text-left text-sm font-label text-accent hover:underline"
            >
              {t("memory.memories.replacedBy", { title: replacement.title })}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
