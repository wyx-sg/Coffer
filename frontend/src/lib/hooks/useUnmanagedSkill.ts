// frontend/src/lib/hooks/useUnmanagedSkill.ts — the file tree of ONE unmanaged
// skill folder, which the Adopt and Delete dialogs list (spec skill-manager
// "Act on an unmanaged skill from the agent's Skills tab"). The list and its
// adopt/delete mutations stay in useAgents.ts. The key nests under the list
// key, so the list's invalidation after an adopt or delete reaches it.
import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { agentUnmanagedSkillFilesKey } from "@/lib/api/queryKeys";

export function useUnmanagedSkillFiles(agentUid: string, location: string, name: string) {
  return useQuery({
    queryKey: agentUnmanagedSkillFilesKey(agentUid, location, name),
    queryFn: async () => (await agentsApi.unmanagedSkillFiles(agentUid, name, location)).root,
    enabled: !!agentUid && !!location && !!name,
  });
}
