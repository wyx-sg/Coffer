// frontend/src/pages/sync/SyncDeletionReviewPage.tsx
//
// Review held deletions (`/sync/deletions`, boards 6.4.10 / 6.4.11): the
// deletion breaker held a round that would delete more than it lets through
// without a person (spec vault-sync "Hold a round that would lose too much").
// The page has no back link; the summary rides in the description line. It
// lists every held file by folder, then offers the two answers —
// delete them here too (asked again, snapshot first) or restore them — and
// either one continues the round and goes back to Sync.
//
// The board draws a hold that came in from another Mac; a hold this Mac would
// push out (`direction: "outgoing"`) reads the same way with its own words.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/status/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncDeletionActions } from "./SyncDeletionActions";
import { SyncDeletionGroups } from "./SyncDeletionGroups";
import { clock } from "./syncConflictFormat";

export function SyncDeletionReviewPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading } = useSyncStop(true);
  const round = data?.stopped && data.round?.kind === "hold" ? data.round : null;
  const hold = round?.hold ?? null;

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

  if (isLoading || !round || !hold) {
    return (
      <div className="space-y-6">
        {header}
        {isLoading ? (
          <Skeleton className="h-64 w-full max-w-[720px]" />
        ) : (
          <EmptyState
            title={t("sync.deletions.empty.title")}
            description={t("sync.deletions.empty.body")}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {header}
      <div className="flex max-w-[720px] flex-col gap-5">
        <SyncDeletionGroups hold={hold} who={who} />
        <SyncDeletionActions hold={hold} who={who} onDone={() => navigate("/sync")} />
      </div>
    </div>
  );
}
