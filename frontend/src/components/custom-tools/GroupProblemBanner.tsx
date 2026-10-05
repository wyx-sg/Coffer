// src/components/custom-tools/GroupProblemBanner.tsx — the banners a group shows for calls that fail (4.2.21: View
// calls, the Activity page on this group's calls · Hand off to <Agent> ▾ · ?) and for a group that is off (4.2.22: Turn on).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { CircleAlert, Power } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { hostOf, toolsOn } from "@/lib/customTools/groups";
import { useTurnOnCustomToolGroup } from "@/lib/hooks/useCustomTools";
import { formatDateTime } from "@/lib/utils";
import { GroupBanner } from "./GroupBanner";

export function GroupFailingBanner({ group }: { group: CustomToolGroup }) {
  const { t } = useTranslation();
  const host = hostOf(group.base_url);
  return (
    <GroupBanner
      tint="err"
      icon={CircleAlert}
      testId="group-banner-failing"
      title={t("customTools.alert.failingTitle", { host })}
      actions={
        <>
          <Button asChild size="sm" variant="outline">
            <Link to={`/activity?tab=mcp&q=${encodeURIComponent(group.name)}`}>
              {t("customTools.group.viewCalls")}
            </Link>
          </Button>
          {group.handoff ? <AgentHandoff prompt={group.handoff.prompt} size="sm" /> : null}
        </>
      }
    >
      {group.last_call_at
        ? t("customTools.alert.failingBodyAt", { time: formatDateTime(group.last_call_at) })
        : t("customTools.alert.failingBody")}
    </GroupBanner>
  );
}

export function GroupOffBanner({ group }: { group: CustomToolGroup }) {
  const { t } = useTranslation();
  const turnOn = useTurnOnCustomToolGroup(group);
  return (
    <GroupBanner
      tint="off"
      icon={Power}
      testId="group-banner-off"
      title={t("customTools.alert.offTitle")}
      actions={
        <Button
          size="sm"
          variant="outline"
          disabled={turnOn.isPending}
          onClick={() => turnOn.mutate()}
        >
          <Power aria-hidden />
          {t("customTools.alert.turnOn")}
        </Button>
      }
    >
      {t("customTools.alert.offBody", { count: toolsOn(group.tools) })}
    </GroupBanner>
  );
}
