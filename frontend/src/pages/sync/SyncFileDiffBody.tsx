// frontend/src/pages/sync/SyncFileDiffBody.tsx
//
// One file's change as the sync pages show it — a round's applied or pushed
// file, a file waiting to push, a file a held round would delete: the
// line-by-line diff, or one line saying why there is none (a secret, a binary
// file, one too large for lines, nothing changed).
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { RoundFileDiff } from "@/lib/api/sync";
import { parseUnifiedDiff } from "./syncConflictFormat";
import { DiffTable } from "./SyncDiffTable";

const NOTE = "text-xs text-text-muted";

export function SyncFileDiffBody({
  query,
  testId,
}: {
  query: UseQueryResult<RoundFileDiff>;
  testId: string;
}) {
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
  return <DiffTable lines={diff.lines} testId={testId} />;
}
