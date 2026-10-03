// src/components/custom-tools/ToolReachCell.tsx — one tool's reach cell in the table (4.2.20): the inherited reach
// control — Same as the group (default) · All agents · Chosen agents — written to the tool's own reach endpoint on
// every change. An override covering every registered agent reads as All agents.
import { useTranslation } from "react-i18next";

import {
  InheritedReachControl,
  type InheritedMode,
} from "@/components/reach/InheritedReachControl";
import type { CustomTool, CustomToolGroup } from "@/lib/api/customTools";
import { useAgents } from "@/lib/hooks/useAgents";
import { useToolReach } from "@/lib/hooks/useToolReach";
import { pickableAgents } from "@/lib/reach/reachState";
import { agentTypeLabel } from "@/lib/agents/display";

interface Props {
  group: CustomToolGroup;
  tool: CustomTool;
}

export function ToolReachCell({ group, tool }: Props) {
  const { t } = useTranslation();
  const { data } = useAgents();
  const registered = pickableAgents(data);
  const reach = useToolReach(group.name, tool.name);
  const override = tool.reach_override;
  const coversAll =
    override !== null && registered.length > 0 && registered.every((a) => override.includes(a.uid));
  const mode: InheritedMode =
    override === null ? "inherited" : coversAll ? "everywhere" : "restricted";

  const reached = registered.filter((a) => group.scope === null || group.scope.includes(a.uid));
  const names = reached.map((a) => (a.type ? agentTypeLabel(a.type) : a.name));
  const inheritedSub =
    names.length === 0
      ? undefined
      : t("customTools.tools.groupGives", {
          group: group.name,
          agents: names.join(t("customTools.editor.and")),
        });

  return (
    <InheritedReachControl
      mode={mode}
      // Narrowing starts from what the group gives, so it is one untick away.
      scope={{ agents: override ?? reached.map((a) => a.uid) }}
      resourceName={tool.name}
      inheritedSub={inheritedSub}
      footnote={t("customTools.tools.reachFootnote")}
      onInherit={() => reach.save(null)}
      onEverywhere={() => reach.save(registered.map((a) => a.uid))}
      onRestricted={(scope, changed) => reach.save(scope.agents, changed ?? null)}
      saveState={reach.state}
      failure={reach.failure}
      ariaLabel={t("customTools.tools.reachOf", { name: tool.name })}
    />
  );
}
