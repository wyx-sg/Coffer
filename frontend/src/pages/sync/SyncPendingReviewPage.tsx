// frontend/src/pages/sync/SyncPendingReviewPage.tsx
//
// Review changes to push (`/sync/pending`, spec vault-sync "Review a file's
// change before acting on it"): every file this Mac has that the remote does
// not have yet, once each however many commits touched it, with who wrote it
// last and when. The chosen file shows its change since the last push. The
// changes go out on their own in the next round; Push now runs that round at
// once, which still pulls first.
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { usePendingFileDiff, useRunSync, useSyncStatus } from "@/lib/hooks/useSync";
import { ChangeMark } from "./SyncChangeMark";
import { SyncReviewDiffPane, SyncReviewNav, SyncReviewShell } from "./SyncReviewShell";
import { pendingFiles, WRITER, type PendingFile } from "./syncPendingFiles";
import { clock } from "./syncTime";

function useWho() {
  const { t } = useTranslation();
  return (file: PendingFile) =>
    `${t(`sync.waiting.writer.${WRITER[file.writer] ?? "coffer"}`)} · ${clock(file.time)}`;
}

export function SyncPendingReviewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { data: status, isPending } = useSyncStatus();
  const run = useRunSync();
  const who = useWho();
  const files = pendingFiles(status?.waiting ?? []);
  const wanted = params.get("path");
  const file = files.find((f) => f.path === wanted) ?? files[0];
  const diff = usePendingFileDiff(file?.path ?? "", file !== undefined);

  const header = (
    <PageHeader
      title={t("sync.pending.title")}
      subtitle={
        files.length > 0
          ? status?.next_round_at
            ? t("sync.pending.sublineAt", {
                files: t("sync.deletions.files", { count: files.length }),
                time: clock(status.next_round_at),
              })
            : t("sync.pending.subline", {
                files: t("sync.deletions.files", { count: files.length }),
              })
          : undefined
      }
    />
  );

  if (isPending || !file) {
    return (
      <div className="space-y-6">
        {header}
        {isPending ? (
          <Skeleton className="h-80 w-full" />
        ) : (
          <EmptyState
            title={t("sync.pending.empty.title")}
            description={t("sync.pending.empty.body")}
          />
        )}
      </div>
    );
  }

  const select = (path: string) => {
    const next = new URLSearchParams(params);
    next.set("path", path);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      {header}
      <SyncReviewShell
        nav={
          <SyncReviewNav
            selected={file.path}
            onSelect={select}
            items={files.map((f) => ({
              path: f.path,
              mark: <ChangeMark status={f.status} />,
              note: who(f),
              testId: `pending-file-${f.path}`,
            }))}
          />
        }
        footer={
          <>
            <p className="text-xs text-text-muted">{t("sync.pending.hint")}</p>
            {run.error ? (
              <p className="text-xs text-danger" role="alert">
                {translateApiError(t, run.error)}
              </p>
            ) : null}
            <div className="ml-auto flex items-center gap-2">
              <Button asChild variant="ghost">
                <Link to="/sync">{t("sync.pending.back")}</Link>
              </Button>
              <Button
                type="button"
                loading={run.isPending}
                onClick={() => run.mutate(undefined, { onSuccess: () => navigate("/sync") })}
              >
                {t("sync.pending.pushNow")}
              </Button>
            </div>
          </>
        }
      >
        <SyncReviewDiffPane path={file.path} status={file.status} note={who(file)} query={diff} />
      </SyncReviewShell>
    </div>
  );
}
