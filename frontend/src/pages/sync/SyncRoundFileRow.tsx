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
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { SyncChange } from "@/lib/api/sync";
import { useRoundFileDiff } from "@/lib/hooks/useSync";
import { cn } from "@/lib/utils";
import { ChangeMark, FILE_ROW } from "./SyncChangeMark";
import { parseUnifiedDiff } from "./syncConflictFormat";
import { DiffTable } from "./SyncDiffTable";

const NOTE = "text-xs text-text-muted";

function DiffBody({ query }: { query: ReturnType<typeof useRoundFileDiff> }) {
  const { t } = useTranslation();
  if (query.isLoading) return <Skeleton className="h-16 w-full" />;
  if (query.error) {
    return (
      <p className="text-xs text-danger" role="alert">
        {translateApiError(t, query.error)}
      </p>
    );
  }
  const data = query.data;
  if (!data) return null;
  if (data.kind === "secret") return <p className={NOTE}>{t("sync.drawer.diffSecret")}</p>;
  if (data.kind === "binary") return <p className={NOTE}>{t("sync.drawer.diffBinary")}</p>;
  if (data.kind === "too_large") return <p className={NOTE}>{t("sync.drawer.diffTooLarge")}</p>;
  const diff = parseUnifiedDiff(data.diff ?? "");
  if (diff.lines.length === 0) return <p className={NOTE}>{t("sync.drawer.diffEmpty")}</p>;
  return <DiffTable lines={diff.lines} testId="sync-round-diff" />;
}

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
          <DiffBody query={query} />
        </div>
      ) : null}
    </li>
  );
}
