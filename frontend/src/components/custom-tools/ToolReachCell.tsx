// src/components/custom-tools/ToolReachCell.tsx — one tool's reach cell in the table (4.2.20): the inherited reach
// control — Same as the group (default) · All agents · Chosen agents — written to the tool's own reach endpoint on
// every change. All agents is the tool's own "every agent" (later ones too), not a list of today's agents.
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

const MODES: Record<CustomTool["reach_mode"], InheritedMode> = {
  inherit: "inherited",
  all: "everywhere",
  chosen: "restricted",
};

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
  const mode = MODES[tool.reach_mode];

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
      onInherit={() => reach.save({ mode: "inherit" })}
      onEverywhere={() => reach.save({ mode: "all" })}
      onRestricted={(scope, changed) =>
        reach.save({ mode: "chosen", agents: scope.agents ?? [] }, changed ?? null)
      }
      saveState={reach.state}
      failure={reach.failure}
      ariaLabel={t("customTools.tools.reachOf", { name: tool.name })}
    />
  );
}
