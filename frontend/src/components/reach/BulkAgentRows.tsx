// src/components/reach/BulkAgentRows.tsx — the per-agent tri-state list of the bulk reach popover.
//
// Foundations-Reach "Bulk reach": one row per registered agent, a tri-state box
// (ticked = every selected item reaches it, dash = some, empty = none), and the
// count "2 of 3"; a changed row reads "2 of 3 → 3 of 3" with the new count in
// accent. The list is live only under Chosen agents, like the single popover.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentEdit } from "@/lib/reach/bulkReach";
import type { PickableAgent } from "@/lib/reach/reachState";
import { cn } from "@/lib/utils";

interface Props {
  agents: PickableAgent[];
  total: number;
  edits: Record<string, AgentEdit>;
  now: (uid: string) => number;
  after: (uid: string) => number;
  active: boolean;
  disabled: boolean;
  onCycle: (uid: string) => void;
}

export function BulkAgentRows({
  agents,
  total,
  edits,
  now,
  after,
  active,
  disabled,
  onCycle,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className={cn("min-h-0 overflow-y-auto", !active && "opacity-[.45]")}>
      {agents.map((agent) => {
        const before = now(agent.uid);
        const next = after(agent.uid);
        const edit = edits[agent.uid] ?? "orig";
        const shown = edit === "orig" ? before : edit === "all" ? total : 0;
        return (
          <label
            key={agent.uid}
            data-testid={`scope-agent-${agent.name}`}
            className="flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-item px-2 transition-colors duration-fast hover:bg-surface-hover"
          >
            <Checkbox
              checked={shown === total && total > 0}
              indeterminate={shown > 0 && shown < total}
              disabled={disabled || !active}
              aria-label={agent.label}
              onChange={() => onCycle(agent.uid)}
            />
            <span aria-hidden className="inline-flex">
              <AgentBadge type={agent.type} name={agent.label} size="md" tooltip={false} />
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-normal text-text">
              {agent.label}
            </span>
            <span className="shrink-0 text-xs text-text-subtle">
              {t("scope.bulkCount", { count: before, total })}
              {next !== before ? (
                <span className="text-accent-text">
                  {" → "}
                  {t("scope.bulkCount", { count: next, total })}
                </span>
              ) : null}
            </span>
          </label>
        );
      })}
    </div>
  );
}
