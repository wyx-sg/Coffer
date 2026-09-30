// src/components/activity/ActivityHeader.tsx — Activity's title with its live mark and ⋯ menu, and the four tabs with their counts.
import { ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/status/StatusDot";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SourceParams } from "@/lib/api/activity";
import { ACTIVITY_TABS, type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import type { TabCount } from "@/lib/hooks/useActivityFeed";
import { ActivityMenu } from "./ActivityMenu";

function CountBadge({ count }: { count: TabCount }) {
  const { i18n, t } = useTranslation();
  if (count.value === undefined) return null;
  const n = count.value.toLocaleString(i18n.language);
  return (
    // How many records exist differs run to run; screenshot tests mask it and
    // give it a fixed width.
    <span data-visual-volatile="count" className="text-2xs font-book text-text-subtle">
      {count.floor ? t("activity.countFloor", { value: n }) : n}
    </span>
  );
}

interface Props {
  tab: ActivityTab;
  onTab: (tab: string) => void;
  counts: Record<ActivityTab, TabCount>;
  /** The daemon's change feed is open. */
  live: boolean;
  /** For the ⋯ menu's export. */
  specs: SourceParams[];
  keep: (r: ActivityRecord) => boolean;
}

export function ActivityHeader({ tab, onTab, counts, live, specs, keep }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader
        icon={ScrollText}
        title={t("activity.title")}
        subtitle={t("activity.subtitle")}
        badges={
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                role="img"
                aria-label={live ? t("activity.live") : t("activity.notLive")}
                className="inline-flex p-1"
              >
                <StatusDot tone={live ? "ok" : "off"} />
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {live ? t("activity.liveHint") : t("activity.notLiveHint")}
            </TooltipContent>
          </Tooltip>
        }
        actions={<ActivityMenu tab={tab} specs={specs} keep={keep} />}
      />
      <Tabs value={tab} onValueChange={onTab}>
        <TabsList>
          {ACTIVITY_TABS.map((value) => (
            <TabsTrigger key={value} value={value}>
              {t(`activity.tabs.${value}`)}
              <CountBadge count={counts[value]} />
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </>
  );
}
