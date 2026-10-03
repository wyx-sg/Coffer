// frontend/src/components/skills/skillSummaries.ts
// The "What will happen" sentences of a change to a skill folder: one for
// Coffer, then one for each agent that holds the skill (it is linked to the
// master, so it sees the change at once). Shared by Update, Restore and the
// Change source review.
import type { ChangeSummaryLine } from "@/lib/changePreview/changeCounts";
import type { SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";

export function useHolderSummaries(
  skill: Pick<SkillOut, "bindings">,
  cofferText: string,
  agentText: string,
): ChangeSummaryLine[] {
  const { data: agents = [] } = useAgents();
  return [
    { agentType: "coffer", agentName: "Coffer", text: cofferText },
    ...skill.bindings.map((b) => {
      const agent = agents.find((a) => a.uid === b.agent_uid);
      return {
        agentType: agent?.type ?? "",
        agentName: agent?.display_name ?? b.agent_name,
        text: agentText,
      };
    }),
  ];
}
