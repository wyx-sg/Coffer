// src/components/custom-tools/GroupRow.tsx — one group in the list pane: name, what is wrong or where it
// points, and its reach. The group's tools are on its own page, not in the row.
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { pickableAgents } from "@/lib/reach/reachState";
import { StatusDot } from "@/components/status/StatusDot";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { healthTone, hostOf } from "@/lib/customTools/groups";
import { secretInState } from "./headerRows";
import { useAgents } from "@/lib/hooks/useAgents";
import { cn } from "@/lib/utils";

interface Props {
  group: CustomToolGroup;
  selected: boolean;
  onOpen: () => void;
}

/** The row's second line: the problem for a group that needs attention. */
function useSubline(group: CustomToolGroup): { text: string; tone: "danger" | "warning" | null } {
  const { t } = useTranslation();
  if (group.health === "attention" && group.secret_state === "pending_approval")
    return { text: t("customTools.list.approvalPending"), tone: "warning" };
  if (group.health === "attention")
    return {
      text: t("customTools.list.secretMissing", { secret: secretInState(group, "missing") }),
      tone: "warning",
    };
  if (group.health === "failing")
    return { text: t("customTools.list.lastCallFailed"), tone: "danger" };
  return {
    text: t("customTools.list.hostTools", {
      host: hostOf(group.base_url),
      count: group.tools.length,
    }),
    tone: null,
  };
}

function Reach({ group }: { group: CustomToolGroup }) {
  const { t } = useTranslation();
  const { data } = useAgents();
  if (!group.enabled) return null;
  if (group.scope === null)
    return <span className="text-xs text-text-muted">{t("customTools.list.allAgents")}</span>;
  const known = pickableAgents(data);
  const agents = group.scope.map((uid) => {
    const found = known.find((a) => a.uid === uid);
    return { type: found?.type ?? "", name: found?.name ?? uid };
  });
  return <AgentBadgeGroup agents={agents} />;
}

export function GroupRow({ group, selected, onOpen }: Props) {
  const sub = useSubline(group);

  return (
    <li>
      <div
        className={cn(
          "flex min-h-[52px] items-center gap-2 rounded-lg px-2.5 transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <button
          type="button"
          aria-current={selected ? "page" : undefined}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left"
          onClick={onOpen}
        >
          <StatusDot tone={healthTone(group.health)} />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-mono text-sm font-label text-text">
              {group.name}
            </span>
            <span
              className={cn(
                "block truncate text-xs",
                sub.tone === "danger"
                  ? "text-danger"
                  : sub.tone === "warning"
                    ? "text-warning"
                    : "text-text-muted",
              )}
            >
              {sub.text}
            </span>
          </span>
          <Reach group={group} />
        </button>
      </div>
    </li>
  );
}
