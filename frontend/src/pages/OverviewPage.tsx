// src/pages/OverviewPage.tsx — the page the app opens on: is everything OK, and what needs me?
//
// "Needs you" first (one row per problem across every area), then a Health
// tile per area, then the last few notable events. Before any agent is
// registered the page is the first-run panel alone (no live mark, nothing to
// have happened yet: Overview boards 1.2.06, 1.2.07). The page follows
// the daemon's event stream: an attention change refetches the list, a
// resource change the lists the tiles read (useDaemonEvents), so rows clear
// themselves as problems resolve.
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { FirstRun } from "@/components/overview/FirstRun";
import { HealthTiles } from "@/components/overview/HealthTiles";
import { LiveMark } from "@/components/overview/LiveMark";
import { NeedsYouList } from "@/components/overview/NeedsYouList";
import { RecentActivity } from "@/components/overview/RecentActivity";
import { useAgents } from "@/lib/hooks/useAgents";
import { useAttention } from "@/lib/hooks/useAttention";
import { useDaemonEvents } from "@/lib/hooks/useDaemonEvents";

export function OverviewPage() {
  const { t } = useTranslation();
  const { live } = useDaemonEvents();
  const attention = useAttention();
  const agents = useAgents();
  const firstRun = agents.data !== undefined && agents.data.length === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("overview.title")}
        subtitle={t("overview.subtitle")}
        actions={firstRun ? null : <LiveMark live={live} checkedAt={attention.dataUpdatedAt} />}
      />
      {firstRun ? (
        <FirstRun />
      ) : (
        <div className="flex flex-col gap-6">
          <NeedsYouList />
          <HealthTiles />
          <RecentActivity />
        </div>
      )}
    </div>
  );
}
