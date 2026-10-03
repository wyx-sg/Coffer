// frontend/src/pages/sync/SyncJoinPreview.tsx — first join, preview (6.4.22).
//
// A machine meets the remote for the first time by JOINING it (spec
// vault-sync "Report a join before applying it"), and a join is explicit: until
// this Mac joins, rounds move nothing. This asks the daemon what joining
// would do — applying nothing — and states it before the button: what comes
// down, by area; how many files are already the same; which differ (left here
// until a person chooses, never overwritten or pushed); what goes up; and that
// nothing is deleted. A remote at an older layout is REPLACED by this Mac's
// vault (spec vault-sync "Refuse a remote at another layout"). A refused
// join (a newer layout, not a vault) shows the daemon's reason, no Join button;
// a push token still waiting for approval says so and offers Secrets.
import { useTranslation } from "react-i18next";

import { LoadError } from "@/components/LoadError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JoinPreview } from "@/lib/api/sync";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { useJoin, useJoinPreview } from "@/lib/hooks/useSyncStop";
import { isApprovalWait } from "@/lib/syncApproval";
import { SyncApprovalWait } from "./SyncApprovalWait";
import { JoinLine } from "./SyncJoinLine";
import { SyncReplaceLines } from "./SyncReplaceLines";
import { areaSummary } from "./syncJoinAreas";
import { roundMoment } from "./syncMachineTimes";

function Lines({ preview }: { preview: JoinPreview }) {
  const { t } = useTranslation();
  const other = preview.pushed_by ?? t("sync.join.otherMacs");
  return (
    <ul className="flex flex-col" data-testid="sync-join-preview">
      <JoinLine
        mark="+"
        testId="sync-join-pulled"
        title={t("sync.join.pulled", { count: preview.pulled_files })}
        body={
          preview.pulled_files > 0
            ? `${areaSummary(t, preview.pulled)}. ${t("sync.join.pulledBody")}`
            : undefined
        }
      />
      <JoinLine
        mark="="
        title={t("sync.join.same", { count: preview.same })}
        body={t("sync.join.sameBody")}
      />
      {preview.differ.length > 0 ? (
        <JoinLine
          mark="≠"
          tone="warn"
          testId="sync-join-differ"
          title={t("sync.join.differ", { count: preview.differ.length })}
          body={t("sync.join.differBody")}
        />
      ) : null}
      {preview.conflicts.length > 0 ? (
        <JoinLine
          mark="!"
          tone="err"
          title={t("sync.join.conflicts", { count: preview.conflicts.length })}
          body={preview.conflicts.join(", ")}
        />
      ) : null}
      <JoinLine
        mark="↑"
        testId="sync-join-pushed"
        title={t("sync.join.pushed", { count: preview.pushed_files })}
        body={preview.pushed_files > 0 ? t("sync.join.pushedBody", { who: other }) : undefined}
      />
      {preview.deleted.length === 0 ? (
        <JoinLine
          mark="−"
          title={t("sync.join.nothingDeleted")}
          body={t("sync.join.nothingDeletedBody")}
        />
      ) : (
        <JoinLine
          mark="−"
          tone="err"
          testId="sync-join-deleted"
          title={t("sync.join.deleted", { count: preview.deleted.length })}
          body={preview.deleted.join(", ")}
        />
      )}
    </ul>
  );
}

export function SyncJoinPreview({
  onBack,
  backPending,
}: {
  onBack: () => void;
  backPending: boolean;
}) {
  const { t, i18n } = useTranslation();
  const preview = useJoinPreview(true);
  const join = useJoin();
  const data = preview.data;
  const refused = data?.refused ?? null;
  const waiting = isApprovalWait(preview.error);
  const replace = data?.kind === "replace";

  return (
    <div className="flex max-w-[680px] flex-col gap-4" data-testid="sync-join">
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-md font-semibold text-text">
            {t(`sync.join.kind.${data?.kind ?? "new"}`)}
          </h2>
          <p className="text-xs text-text-muted">
            {data?.pushed_by
              ? t("sync.join.lastPushed", {
                  who: data.pushed_by,
                  when: data.pushed_at
                    ? roundMoment(data.pushed_at, new Date(), t, i18n.language)
                    : "—",
                })
              : null}{" "}
            {replace ? t("sync.join.replaceLead") : t("sync.join.lead")}
          </p>
        </div>
        {preview.isLoading ? (
          <div className="flex flex-col gap-2 py-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : waiting ? (
          <SyncApprovalWait onReview={openApprovalsSheet} onRetry={() => void preview.refetch()} />
        ) : preview.error ? (
          <LoadError
            className="py-2"
            error={preview.error}
            onRetry={() => void preview.refetch()}
          />
        ) : data ? (
          <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
            {replace ? <SyncReplaceLines preview={data} /> : <Lines preview={data} />}
          </div>
        ) : null}
        {refused ? (
          <p className="py-2 text-sm text-danger" role="alert">
            {refused}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          disabled={!data || refused !== null}
          loading={join.isPending}
          onClick={() => join.mutate()}
        >
          {replace
            ? join.isPending
              ? t("sync.join.replacing")
              : t("sync.join.replace")
            : join.isPending
              ? t("sync.join.joining")
              : t("sync.join.join")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={join.isPending}
          loading={backPending}
          onClick={onBack}
        >
          {t("sync.setup.back")}
        </Button>
        <span className="ml-auto text-xs text-text-subtle">{t("sync.join.snapshot")}</span>
      </div>
    </div>
  );
}
