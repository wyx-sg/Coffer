// frontend/src/pages/sync/SyncConflictDiff.tsx
//
// "What changes on this Mac" when the other Mac's version is taken: the
// daemon's unified diff from this Mac's version to theirs (`take_theirs` of
// `GET /sync/stop/files/versions`), as rows with old and new line numbers —
// the same diff table the change previews draw. For a file an agent merged,
// `which="merged"` shows the merge (`merged_diff`) against this Mac's version
// instead. A binary file has no line-by-line diff and says so.
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { OpChip } from "@/components/change-preview/OpChip";
import type { DiffLine } from "@/lib/changePreview/changeCounts";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useFileVersions } from "@/lib/hooks/useSyncStop";
import { cn } from "@/lib/utils";
import { parseUnifiedDiff } from "./syncConflictFormat";

const GUTTER = "pr-2 text-right text-2xs leading-5 text-text-subtle";
const TONE: Record<DiffLine["kind"], string> = {
  context: "",
  hunk: "",
  add: "bg-success-soft",
  remove: "bg-danger-soft",
};
const SIGN: Record<DiffLine["kind"], [string, string]> = {
  context: ["", "text-text-subtle"],
  hunk: ["", "text-text-subtle"],
  add: ["+", "text-success"],
  remove: ["−", "text-danger"],
};

function Row({ line, first }: { line: DiffLine; first: boolean }) {
  if (line.kind === "hunk") {
    return (
      <div
        className={cn(
          "truncate whitespace-nowrap border-b border-border-subtle bg-surface-sunken px-3 py-0.5 text-2xs leading-5 text-text-subtle",
          !first && "border-t",
        )}
      >
        {line.text}
      </div>
    );
  }
  const [symbol, tone] = SIGN[line.kind];
  return (
    <div
      data-line={line.kind}
      className={cn("grid grid-cols-[34px_34px_16px_minmax(0,1fr)]", TONE[line.kind])}
    >
      <span className={GUTTER}>{line.oldNo ?? ""}</span>
      <span className={cn(GUTTER, "border-r border-border-subtle")}>{line.newNo ?? ""}</span>
      <span aria-hidden className={cn("text-center", tone)}>
        {symbol}
      </span>
      <span className="overflow-hidden text-ellipsis whitespace-pre pr-2.5 text-text">
        {line.text}
      </span>
    </div>
  );
}

export function SyncConflictDiff({
  path,
  which = "theirs",
}: {
  path: string;
  which?: "theirs" | "merged";
}) {
  const { t } = useTranslation();
  const versions = useFileVersions(path, true);
  const data = versions.data;
  const text = which === "merged" ? (data?.merged_diff ?? "") : data?.take_theirs;
  const diff = data && !data.binary ? parseUnifiedDiff(text ?? "") : null;
  // Taking a deletion removes the file here; taking a file this Mac lacks adds it.
  const op =
    !data || data.binary || which === "merged"
      ? "modify"
      : data.theirs === null
        ? "remove"
        : data.ours === null
          ? "add"
          : "modify";

  let body;
  if (versions.isLoading) body = <Skeleton className="h-24 w-full" />;
  else if (versions.error) {
    body = (
      <p className="text-xs text-danger" role="alert">
        {translateApiError(t, versions.error)}
      </p>
    );
  } else if (data?.binary)
    body = <p className="text-xs text-text-muted">{t("sync.resolve.binary")}</p>;
  else if (!diff || diff.lines.length === 0) {
    body = <p className="text-xs text-text-muted">{t("sync.resolve.noDiff")}</p>;
  } else {
    body = (
      <div
        className="overflow-hidden rounded-lg border border-border bg-surface-raised font-mono text-xs leading-5"
        data-testid="sync-conflict-diff"
      >
        {diff.lines.map((line, i) => (
          <Row key={i} line={line} first={i === 0} />
        ))}
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-2.5" aria-label={t("sync.resolve.whatChanges")}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-text-muted">
          {t("sync.resolve.whatChanges")}
        </span>
        <OpChip op={op} />
        {diff ? <LineCounts added={diff.added} removed={diff.removed} className="ml-auto" /> : null}
      </div>
      {body}
    </section>
  );
}
