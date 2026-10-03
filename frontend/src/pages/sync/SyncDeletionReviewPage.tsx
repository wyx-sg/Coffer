// frontend/src/pages/sync/SyncDeletionReviewPage.tsx
//
// Review held deletions (`/sync/deletions`, boards 6.5.09 / 6.5.28): the
// deletion breaker held a round that would delete more than it lets through
// without a person (spec vault-sync "Hold a round that would lose too much").
// The page lists every held file by folder, then offers the two answers —
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

const CHIP =
  "inline-flex h-5 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted";

export function SyncDeletionReviewPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading } = useSyncStop(true);
  const round = data?.stopped && data.round?.kind === "hold" ? data.round : null;
  const hold = round?.hold ?? null;

  const header = (
    <PageHeader
      title={t("sync.deletions.title")}
      badges={hold ? <StatusPill tone="warn">{t("sync.deletions.pill")}</StatusPill> : null}
      subtitle={
        round && hold
          ? t(`sync.deletions.subline.${hold.direction}`, {
              time: clock(round.raised_at, i18n.language),
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

  const count = hold.paths.length;
  const who =
    hold.direction === "outgoing"
      ? t("sync.deletions.thisMac")
      : hold.machines.join(", ") || t("sync.deletions.anotherMachine");

  return (
    <div className="space-y-6">
      {header}
      <div className="flex max-w-[720px] flex-col gap-4">
        <div className="flex flex-wrap items-center gap-1.5" data-testid="sync-deletions-summary">
          <span className={CHIP}>{t("sync.deletions.files", { count })}</span>
          <span className={CHIP}>{t("sync.deletions.folders", { count: hold.groups.length })}</span>
          <span className={CHIP}>{t("sync.deletions.deletedOn", { machine: who })}</span>
        </div>
        <SyncDeletionGroups hold={hold} who={who} />
        <SyncDeletionActions hold={hold} who={who} onDone={() => navigate("/sync")} />
      </div>
    </div>
  );
}
