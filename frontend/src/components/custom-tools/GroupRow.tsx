// src/components/custom-tools/GroupRow.tsx — one group in the list pane: name, what is wrong or where it
// points, its reach, and — expanded — its tools.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { reachLabel, reachModeOf } from "@/components/reach/reachState";
import { StatusDot } from "@/components/status/StatusDot";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { groupScope, healthTone, hostOf } from "@/lib/customTools/groups";
import { cn } from "@/lib/utils";

interface Props {
  group: CustomToolGroup;
  selected: boolean;
  onOpen: () => void;
}

/** The row's second line: the problem for a group that needs attention. */
function useSubline(group: CustomToolGroup): { text: string; problem: boolean } {
  const { t } = useTranslation();
  const secret = group.auth?.secret ?? "";
  if (group.health === "attention" && group.secret_state === "pending_approval")
    return { text: t("customTools.list.approvalPending", { secret }), problem: true };
  if (group.health === "attention")
    return { text: t("customTools.list.secretMissing", { secret }), problem: true };
  if (group.health === "failing")
    return { text: t("customTools.list.lastCallFailed"), problem: true };
  return {
    text: t("customTools.list.hostTools", {
      host: hostOf(group.base_url),
      count: group.tools.length,
    }),
    problem: false,
  };
}

export function GroupRow({ group, selected, onOpen }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const sub = useSubline(group);
  const scope = groupScope(group);
  const reach = reachLabel(t, reachModeOf({ enabled: group.enabled, scope }), scope);

  return (
    <li>
      <div
        className={cn(
          "flex min-h-[56px] items-center gap-1 rounded-lg pr-2 transition-colors duration-fast",
          selected ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
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
        <button
          type="button"
          aria-current={selected ? "page" : undefined}
          className="flex min-w-0 flex-1 items-center gap-2 py-2 text-left"
          onClick={onOpen}
        >
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <StatusDot tone={healthTone(group.health)} />
              <span className="truncate font-mono text-sm font-label text-text">{group.name}</span>
            </span>
            <span
              className={cn(
                "block truncate pl-[15px] text-xs",
                sub.problem
                  ? group.health === "failing"
                    ? "text-danger"
                    : "text-warning"
                  : "text-text-muted",
              )}
            >
              {sub.text}
            </span>
          </span>
          <Badge variant="secondary">{reach}</Badge>
        </button>
      </div>
      {expanded ? (
        <ul className="mb-1 ml-8 space-y-0.5 border-l border-border-subtle pl-3">
          {group.tools.map((tool) => (
            <li key={tool.name} className="flex items-center gap-2 py-0.5 text-xs">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-text">{tool.name}</span>
                <span className="block truncate font-mono text-text-muted">
                  {tool.method} {tool.path}
                </span>
              </span>
              <span className={tool.enabled ? "text-text-muted" : "text-text-subtle"}>
                {tool.enabled ? t("customTools.tools.on") : t("customTools.tools.off")}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}
