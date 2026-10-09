// src/components/custom-tools/GroupRow.tsx — one group in the list pane: name, what is wrong or where it
// points, and its reach. The group's tools are on its own page, not in the row. The checkbox feeds the
// selection bar: it shows on hover or focus, and on every row while any is ticked.
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { pickableAgents } from "@/lib/reach/reachState";
import { StatusDot } from "@/components/status/StatusDot";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { healthTone, hostOf } from "@/lib/customTools/groups";
import { useSecretChoices } from "@/components/secret/useSecretChoices";
import { secretInState } from "./headerRows";
import { useAgents } from "@/lib/hooks/useAgents";
import { cn } from "@/lib/utils";

interface Props {
  group: CustomToolGroup;
  selected: boolean;
  onOpen: () => void;
  /** Any row is ticked: every checkbox shows. */
  selecting?: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

/** The row's second line: the problem for a group that needs attention, else where it points — its host, or
 *  how many environments it has. */
function useSubline(group: CustomToolGroup): { text: string; tone: "danger" | "warning" | null } {
  const { t } = useTranslation();
  const { displayOf } = useSecretChoices();
  if (group.health === "attention" && group.secret_state === "pending_approval")
    return { text: t("customTools.list.approvalPending"), tone: "warning" };
  if (group.health === "attention" && group.secret_state === "rejected")
    return { text: t("customTools.list.approvalRejected"), tone: "warning" };
  if (group.health === "attention")
    return {
      text: t("customTools.list.secretMissing", {
        secret: displayOf(secretInState(group, "missing")),
      }),
      tone: "warning",
    };
  if (group.health === "failing")
    return { text: t("customTools.list.lastCallFailed"), tone: "danger" };
  const envs = group.environments?.length ?? 0;
  return {
    // A group with several environments has no one host: the row counts them.
    text:
      envs > 1
        ? t("customTools.list.envsTools", { envs, count: group.tools.length })
        : t("customTools.list.hostTools", {
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

export function GroupRow({
  group,
  selected,
  onOpen,
  selecting = false,
  checked,
  onCheckedChange,
}: Props) {
  const { t } = useTranslation();
  const sub = useSubline(group);

  return (
    <li>
      <div
        className={cn(
          "group flex min-h-[52px] items-center gap-2 rounded-lg pl-2.5 pr-2.5 transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <span
          className={cn(
            "shrink-0 items-center",
            selecting || checked
              ? "inline-flex"
              : "hidden group-focus-within:inline-flex group-hover:inline-flex",
          )}
        >
          <Checkbox
            checked={checked}
            onChange={(e) => onCheckedChange(e.target.checked)}
            aria-label={`${t("common.bulk.selectRow")}: ${group.name}`}
          />
        </span>
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
