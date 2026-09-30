// src/components/custom-tools/GroupRow.tsx — one group in the list pane: name, what is wrong or where it
// points, its reach, and — expanded — its tools with Open group.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { pickableAgents } from "@/components/reach/reachState";
import { StatusDot } from "@/components/status/StatusDot";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { healthTone, hostOf } from "@/lib/customTools/groups";
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
  const secret = group.auth?.secret ?? "";
  if (group.health === "attention" && group.secret_state === "pending_approval")
    return { text: t("customTools.list.approvalPending", { secret }), tone: "warning" };
  if (group.health === "attention")
    return { text: t("customTools.list.secretMissing", { secret }), tone: "warning" };
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
  if (!group.enabled)
    return <span className="text-xs text-text-muted">{t("customTools.tools.off")}</span>;
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
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const sub = useSubline(group);

  return (
    <li>
      <div
        className={cn(
          "flex min-h-[52px] items-center gap-2 rounded-lg pl-2.5 pr-1 transition-colors duration-fast",
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
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={t(expanded ? "customTools.list.collapse" : "customTools.list.expand", {
            name: group.name,
          })}
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-item text-text-subtle hover:text-text"
          onClick={() => setExpanded((v) => !v)}
        >
          <ChevronRight
            aria-hidden
            className={cn("size-3.5 transition-transform duration-fast", expanded && "rotate-90")}
          />
        </button>
      </div>
      {expanded ? (
        <ul className="mb-1 ml-6 space-y-1 py-1 pr-2">
          {group.tools.map((tool) => (
            <li key={tool.name} className="flex items-center gap-2 text-xs">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-text">{tool.name}</span>
                <span className="block truncate text-text-muted">
                  {tool.method} {tool.path}
                </span>
              </span>
              <span className="text-text-muted">
                {tool.enabled ? t("customTools.tools.on") : t("customTools.tools.off")}
              </span>
            </li>
          ))}
          <li>
            <button
              type="button"
              className="text-xs font-label text-accent-text hover:underline"
              onClick={onOpen}
            >
              {t("customTools.list.openGroup")}
            </button>
          </li>
        </ul>
      ) : null}
    </li>
  );
}
