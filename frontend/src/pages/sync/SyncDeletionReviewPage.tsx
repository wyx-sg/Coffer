// frontend/src/pages/sync/SyncDeletionReviewPage.tsx
//
// Review held deletions (`/sync/deletions`, boards 6.4.10 / 6.4.11): the
// deletion breaker held a round that would delete more than it lets through
// without a person (spec vault-sync "Hold a round that would lose too much").
// The summary rides in the description line. The shared review shape: every
// held file down the left, folder by folder; the chosen file on the right,
// its whole text as the lines a delete removes; the two answers in the foot —
// Keep the files or Delete N files — each acting at once, because the person
// has read what a delete removes. Either continues the round and goes back to
// Sync.
//
// The board draws a hold that came in from another Mac; a hold this Mac would
// push out (`direction: "outgoing"`) reads the same way with its own words.
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import { useHeldFileDiff } from "@/lib/hooks/useSync";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { ChangeMark } from "./SyncChangeMark";
import { SyncDeletionActions } from "./SyncDeletionActions";
import { SyncReviewDiffPane, SyncReviewNav, SyncReviewShell } from "./SyncReviewShell";
import { clock, folderLabel } from "./syncConflictFormat";

export function SyncDeletionReviewPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { data, isLoading } = useSyncStop(true);
  const round = data?.stopped && data.round?.kind === "hold" ? data.round : null;
  const hold = round?.hold ?? null;
  const files = (hold?.groups ?? []).flatMap((g) =>
    g.paths.map((path) => ({ path, folder: g.folder })),
  );
  const wanted = params.get("path");
  const file = files.find((f) => f.path === wanted) ?? files[0];
  const diff = useHeldFileDiff(file?.path ?? "", file !== undefined);

  const who =
    hold?.direction === "outgoing"
      ? t("sync.deletions.thisMac")
      : (hold?.machines.join(", ") ?? "") || t("sync.deletions.anotherMachine");

  const header = (
    <PageHeader
      title={t("sync.deletions.title")}
      badges={hold ? <StatusPill tone="warn">{t("sync.deletions.pill")}</StatusPill> : null}
      subtitle={
        round && hold
          ? t(`sync.deletions.subline.${hold.direction}`, {
              time: clock(round.raised_at, i18n.language),
              files: t("sync.deletions.files", { count: hold.paths.length }),
              folders: t("sync.deletions.folders", { count: hold.groups.length }),
              machine: who,
            })
          : undefined
      }
    />
  );

  if (isLoading || !round || !hold || !file) {
    return (
      <div className="space-y-6">
        {header}
        {isLoading ? (
          <Skeleton className="h-80 w-full" />
        ) : (
          <EmptyState
            title={t("sync.deletions.empty.title")}
            description={t("sync.deletions.empty.body")}
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
              mark: <ChangeMark status="removed" />,
              note: folderLabel(t, f.folder),
              testId: `held-file-${f.path}`,
            }))}
          />
        }
        footer={<SyncDeletionActions hold={hold} who={who} onDone={() => navigate("/sync")} />}
      >
        <SyncReviewDiffPane
          path={file.path}
          status="removed"
          note={t("sync.deletions.deletedOn", { machine: who })}
          query={diff}
        />
      </SyncReviewShell>
    </div>
  );
}
