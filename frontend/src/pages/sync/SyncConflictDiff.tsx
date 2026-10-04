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
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useFileVersions } from "@/lib/hooks/useSyncStop";
import { parseUnifiedDiff } from "./syncConflictFormat";
import { DiffTable } from "./SyncDiffTable";

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
    body = <DiffTable lines={diff.lines} />;
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
