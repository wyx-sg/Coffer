// frontend/src/pages/sync/SyncStopBanner.tsx
//
// A round that stopped for a person (6.5.05 conflicts, 6.5.08 deletions
// held): what happened, that nothing was checked out or pushed, and the one
// way forward — Resolve conflicts or Review deletions, each its own page. The
// files themselves are listed under the area tiles by `SyncStoppedCard`.
//
// The stop is read for the name of the Mac on the other side, which is what
// makes "changed the same lines" a sentence a person can picture.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncBannerCard } from "./SyncBanner";

interface Props {
  kind: "conflicts" | "held";
  count: number;
}

export function SyncStopBanner({ kind, count }: Props) {
  const { t } = useTranslation();
  const { data } = useSyncStop(true);
  const round = data?.stopped ? data.round : null;

  if (kind === "conflicts") {
    const peer =
      round?.files.map((f) => f.theirs_machine).find(Boolean) ?? t("sync.banner.anotherMac");
    return (
      <SyncBannerCard
        icon={AlertTriangle}
        tone="err"
        title={t("sync.banner.stoppedConflicts", { count })}
      >
        <p className="max-w-prose text-sm text-text-muted">
          {t("sync.banner.stoppedConflictsBody", { peer })}
        </p>
        <div>
          <Button asChild>
            <Link to="/sync/conflicts">{t("sync.banner.resolveConflicts")}</Link>
          </Button>
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
    >
      <p className="max-w-prose text-sm text-text-muted">{t("sync.banner.heldBody")}</p>
      <div>
        <Button asChild>
          <Link to="/sync/deletions">{t("sync.banner.reviewDeletions")}</Link>
        </Button>
      </div>
    </SyncBannerCard>
  );
}
