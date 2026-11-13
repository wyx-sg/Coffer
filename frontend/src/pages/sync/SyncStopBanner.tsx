// frontend/src/pages/sync/SyncStopBanner.tsx
//
// A round that stopped on conflicts (6.4.05): what happened, that nothing was
// checked out or pushed, and the ways forward — Resolve conflicts (a secondary
// button: the page's one primary is Sync now, which is disabled while the
// round is stopped) and Ask an agent, which hands every file an agent may
// merge over in one prompt. × is Ignore, the same as on Overview. The files
// themselves are on the Resolve conflicts page, never listed on the Status tab.
//
// The stop is read for the name of the Mac on the other side, which is what
// makes "changed the same lines" a sentence a person can picture.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { useHandoffRequest, useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncBannerCard } from "./SyncBanner";
import { STOP_REASON, useSyncIgnore } from "./useSyncIgnore";

export function SyncStopBanner({ count }: { count: number }) {
  const { t } = useTranslation();
  const { data } = useSyncStop(true);
  const { isIgnored, ignorer } = useSyncIgnore();
  const handoff = useHandoffRequest();
  const round = data?.stopped ? data.round : null;
  if (isIgnored(STOP_REASON)) return null;

  const peer =
    round?.files.map((f) => f.theirs_machine).find(Boolean) ?? t("sync.banner.anotherMac");
  const mergeable = round?.files.some((f) => f.agent_mergeable && f.answer === null) ?? false;
  return (
    <SyncBannerCard
      icon={AlertTriangle}
      tone="err"
      title={t("sync.banner.stoppedConflicts", { count })}
      onIgnore={ignorer(STOP_REASON)}
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
