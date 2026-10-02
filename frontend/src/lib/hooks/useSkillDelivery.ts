// frontend/src/lib/hooks/useSkillDelivery.ts
// Change which agents one skill is delivered to, from the Delivery tab. It is
// the same write the header's reach control makes — the resource's scope
// (PUT /resources/{uid}/scope, plus enable when the skill is off) — so the
// header and the tab read one stored answer and both refresh through the
// shared invalidation in useUpdateResourceScope.
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { useEnableResource } from "@/lib/hooks/useResourceMutations";
import { useUpdateResourceScope } from "@/lib/hooks/useScope";
import { deliveryWrite } from "@/lib/skills/delivery";

export function useSkillDelivery(skill: SkillOut, agents: readonly AgentOut[]) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const update = useUpdateResourceScope("skill", skill.uid);
  const enable = useEnableResource();
  // Which agents have a change in flight, and in which direction.
  const [pending, setPending] = useState<Record<string, "on" | "off">>({});

  const set = useCallback(
    async (agent: AgentOut, on: boolean) => {
      const write = deliveryWrite(
        skill,
        agent.uid,
        on,
        agents.map((a) => a.uid),
      );
      if (!write) return;
      setPending((p) => ({ ...p, [agent.uid]: on ? "on" : "off" }));
      try {
        if (write.enable) await enable.mutateAsync({ kind: "skill", uid: skill.uid });
        if (write.scope) await update.mutateAsync(write.scope);
        toast.success(
          t(on ? "skills.delivery.toast.on" : "skills.delivery.toast.off", {
            agent: agent.display_name,
          }),
        );
      } catch {
        // The mutation hooks already toasted the API error.
      } finally {
        setPending((p) => {
          const rest = { ...p };
          delete rest[agent.uid];
          return rest;
        });
      }
    },
    [skill, agents, enable, update, toast, t],
  );

  // Every agent at once: "every agent" is the null scope, "none" the empty list.
  const setAll = useCallback(
    async (on: boolean) => {
      const mark: Record<string, "on" | "off"> = {};
      for (const a of agents) mark[a.uid] = on ? "on" : "off";
      setPending(mark);
      try {
        if (on && !skill.enabled) await enable.mutateAsync({ kind: "skill", uid: skill.uid });
        await update.mutateAsync(on ? null : { agents: [] });
        toast.success(t(on ? "skills.delivery.toast.allOn" : "skills.delivery.toast.allOff"));
      } catch {
        // The mutation hooks already toasted the API error.
      } finally {
        setPending({});
      }
    },
    [skill, agents, enable, update, toast, t],
  );

  return { pending, set, setAll };
}
