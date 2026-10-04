// src/components/activity/ActivityHeader.tsx — Activity's title with its live mark and Export, and the four tabs.
//
// Design 6.2.01: the title, "● Live" (a dot and the word; "Reconnecting…" when
// the daemon's change feed is closed), the one-line description, a ghost
// "Export ⌄" on the right. Tabs carry no counts; a tab whose log failed to
// load shows a warning icon.
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { StatusDot } from "@/components/status/StatusDot";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SourceParams } from "@/lib/api/activity";
import { ACTIVITY_TABS, type ActivityRecord, type ActivityTab } from "@/lib/activity/records";
import { ExportMenu } from "./ExportMenu";

interface Props {
  tab: ActivityTab;
  onTab: (tab: string) => void;
  /** Tabs whose log could not be loaded. */
  failedTabs: ReadonlySet<ActivityTab>;
  /** The daemon's change feed is open. */
  live: boolean;
  /** No records at all yet: there is nothing to export. */
  empty: boolean;
  /** For the export. */
  specs: SourceParams[];
  keep: (r: ActivityRecord) => boolean;
}

export function ActivityHeader({ tab, onTab, failedTabs, live, empty, specs, keep }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader
        title={t("activity.title")}
        subtitle={t("activity.subtitle")}
        badges={
          <span className="inline-flex items-center gap-[5px] text-xs text-text-muted">
            <StatusDot tone={live ? "ok" : "off"} />
            {live ? t("activity.live") : t("activity.reconnecting")}
          </span>
        }
        actions={empty ? null : <ExportMenu tab={tab} specs={specs} keep={keep} />}
      />
      <Tabs value={tab} onValueChange={onTab}>
        <TabsList>
          {ACTIVITY_TABS.map((value) => (
            <TabsTrigger key={value} value={value}>
              {t(`activity.tabs.${value}`)}
              {failedTabs.has(value) ? (
                <AlertTriangle
                  role="img"
                  aria-label={t("activity.tabFailed")}
                  className="size-[13px] text-warning"
                />
              ) : null}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </>
  );
}
