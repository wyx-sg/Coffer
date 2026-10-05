// frontend/src/pages/sync/SyncStopBanner.tsx
//
// A round that stopped for a person (6.4.05 conflicts, 6.4.09 deletions
// held): what happened, that nothing was checked out or pushed, and the ways
// forward — Resolve conflicts (a secondary button: the page's one primary is
// Sync now, which is disabled while the round is stopped) or Review deletions,
// each its own page; for conflicts also Ask an agent, which hands every file
// an agent may merge over in one prompt. × is Ignore, the same as on Overview.
// The files themselves are on those pages, never listed on the Status tab.
//
// The stop is read for the name of the Mac on the other side, which is what
// makes "changed the same lines" a sentence a person can picture.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, Trash2 } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { useHandoffRequest, useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncBannerCard } from "./SyncBanner";
import { STOP_REASON, useSyncIgnore } from "./useSyncIgnore";

interface Props {
  kind: "conflicts" | "held";
  count: number;
}

export function SyncStopBanner({ kind, count }: Props) {
  const { t } = useTranslation();
  const { data } = useSyncStop(true);
  const { isIgnored, ignorer } = useSyncIgnore();
  const handoff = useHandoffRequest();
  const round = data?.stopped ? data.round : null;
  const reason = STOP_REASON[kind];
  if (isIgnored(reason)) return null;

  if (kind === "conflicts") {
    const peer =
      round?.files.map((f) => f.theirs_machine).find(Boolean) ?? t("sync.banner.anotherMac");
    const mergeable = round?.files.some((f) => f.agent_mergeable && f.answer === null) ?? false;
    return (
      <SyncBannerCard
        icon={AlertTriangle}
        tone="err"
        title={t("sync.banner.stoppedConflicts", { count })}
        onIgnore={ignorer(reason)}
      >
        <p className="max-w-prose text-sm text-text-muted">
          {t("sync.banner.stoppedConflictsBody", { peer })}
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button asChild variant="outline" size="sm">
            <Link to="/sync/conflicts">{t("sync.banner.resolveConflicts")}</Link>
          </Button>
          {mergeable ? <AgentHandoff size="sm" prompt={({ agent }) => handoff({ agent })} /> : null}
        </div>
      </SyncBannerCard>
    );
  }

  const hold = round?.hold ?? null;
  const incoming = hold?.direction !== "outgoing";
  const peer = hold?.machines[0] ?? t("sync.banner.anotherMac");
  return (
    <SyncBannerCard
      icon={Trash2}
      tone="err"
      title={
        incoming
          ? t("sync.banner.heldIncoming", { count, peer })
          : t("sync.banner.heldOutgoing", { count })
      }
      onIgnore={ignorer(reason)}
    >
      <p className="max-w-prose text-sm text-text-muted">{t("sync.banner.heldBody")}</p>
      <div className="pt-1">
        <Button asChild variant="outline" size="sm">
          <Link to="/sync/deletions">{t("sync.banner.reviewDeletions")}</Link>
        </Button>
      </div>
    </SyncBannerCard>
  );
}
