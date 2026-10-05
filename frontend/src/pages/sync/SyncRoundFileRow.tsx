// frontend/src/pages/sync/SyncRoundFileRow.tsx
//
// One file of a round's Applied or Pushed list (spec vault-sync "Show what a
// round changed in each file"): a row that opens in place to its line-by-line
// diff, fetched when it is first opened, with the +N −M counts beside the path
// once they are known. A secret, a binary file and one too large for lines say
// so instead; a round whose commits are gone says that.
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import type { SyncChange } from "@/lib/api/sync";
import { useRoundFileDiff } from "@/lib/hooks/useSync";
import { cn } from "@/lib/utils";
import { ChangeMark, FILE_ROW } from "./SyncChangeMark";
import { SyncFileDiffBody } from "./SyncFileDiffBody";

export function RoundFileRow({
  runId,
  side,
  change,
}: {
  runId: number | null;
  side: "applied" | "pushed";
  change: SyncChange;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const query = useRoundFileDiff(runId ?? 0, change.path, side, open && runId !== null);
  const counts = query.data?.kind === "text" ? query.data : null;
  const label = (
    <>
      <ChangeMark status={change.status} />
      <span className="min-w-0 flex-1 truncate text-left font-mono text-xs text-text">
        {change.path}
      </span>
    </>
  );
  if (runId === null) return <li className={FILE_ROW}>{label}</li>;
  return (
    <li className="border-b border-border-subtle last:border-b-0">
      <div className={cn(FILE_ROW, "border-b-0")}>
        <button
          type="button"
          aria-expanded={open}
          aria-label={t("sync.drawer.showDiff", { path: change.path })}
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2.5 self-stretch text-left"
        >
          <ChevronRight
            aria-hidden
            className={cn(
              "size-3 shrink-0 text-text-subtle transition-transform",
              open && "rotate-90",
            )}
          />
          {label}
        </button>
        {counts ? <LineCounts added={counts.added} removed={counts.removed} /> : null}
      </div>
      {open ? (
        <div className="px-3 pb-3">
          <SyncFileDiffBody query={query} testId="sync-round-diff" />
        </div>
      ) : null}
    </li>
  );
}
