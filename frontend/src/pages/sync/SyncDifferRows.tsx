// frontend/src/pages/sync/SyncDifferRows.tsx
//
// The bordered list of files a person has to settle, shared by the stopped
// round's "Changed on both Macs" (6.4.05) and a first join's "Differ from this
// Mac" (6.4.23): path, which area and when each Mac changed it, and at the end
// a dot and a word for where it stands, in a box of its own under the title the
// caller draws. A row opens Resolve conflicts at that file. More than five rows fold behind "Show all" (principle 21).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ShowAllRow } from "@/components/LongList";
import { useLongList } from "@/components/useLongList";
import type { ConflictFile } from "@/lib/api/sync";
import { cn } from "@/lib/utils";
import { areaLabel, clock, otherMachine } from "./syncConflictFormat";

type RowTone = "ok" | "err" | "warn";

const DOT: Record<RowTone, string> = {
  ok: "bg-success",
  err: "bg-danger",
  warn: "bg-warning",
};
const WORD: Record<RowTone, string> = {
  ok: "text-success",
  err: "text-danger",
  warn: "text-warning",
};

interface Props {
  files: ConflictFile[];
  /** Where a row leads. */
  href: (file: ConflictFile) => string;
  /** The row's end: a tone for the dot and the word beside it. */
  status: (file: ConflictFile) => { tone: RowTone; label: string };
  testId: (file: ConflictFile) => string;
  listTestId?: string;
}

export function SyncDifferRows({ files, href, status, testId, listTestId }: Props) {
  const { t, i18n } = useTranslation();
  const { visible, shown, total, collapsed, expand, listClassName } = useLongList(files);
  return (
    <div
      className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface-raised"
      data-testid={listTestId}
    >
      <ul className={cn("[&>li+li]:border-t [&>li+li]:border-border-subtle", listClassName)}>
        {visible.map((file) => {
          const end = status(file);
          return (
            <li key={file.path}>
              <Link
                to={href(file)}
                className="flex min-h-12 min-w-0 items-center gap-2.5 px-3 py-1.5 transition-colors duration-fast hover:bg-surface-hover"
                data-testid={testId(file)}
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate font-mono text-xs text-text">{file.path}</span>
                  <span className="text-xs text-text-muted">
                    {t("sync.conflicts.row", {
                      area: areaLabel(t, file.area),
                      mine: clock(file.ours_time, i18n.language),
                      machine: otherMachine(t, file),
                      theirs: clock(file.theirs_time, i18n.language),
                    })}
                  </span>
                </span>
                <span
                  className={cn(
                    "ml-auto inline-flex shrink-0 items-center gap-[5px] whitespace-nowrap text-xs",
                    WORD[end.tone],
                  )}
                >
                  <span
                    aria-hidden
                    className={cn("size-1.5 shrink-0 rounded-full", DOT[end.tone])}
                  />
                  {end.label}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      {collapsed ? <ShowAllRow shown={shown} total={total} onShowAll={expand} /> : null}
    </div>
  );
}
