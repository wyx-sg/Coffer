// frontend/src/lib/hooks/useUnmanagedSkill.ts — TanStack Query bindings for the
// read-only preview of ONE unmanaged skill folder (spec skill-manager "Preview
// an unmanaged skill read-only"). The list and its adopt/delete mutations stay
// in useAgents.ts; these three reads back the detail page. Every key nests under
// the list key, so the list's invalidation after an adopt or delete reaches them.
import { useQuery } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import {
  agentUnmanagedSkillFileKey,
  agentUnmanagedSkillFilesKey,
  agentUnmanagedSkillKey,
} from "@/lib/api/queryKeys";

export function useUnmanagedSkill(agentUid: string, location: string, name: string) {
  return useQuery({
    queryKey: agentUnmanagedSkillKey(agentUid, location, name),
    queryFn: () => agentsApi.unmanagedSkill(agentUid, name, location),
    enabled: !!agentUid && !!location && !!name,
  });
}

export function useUnmanagedSkillFiles(agentUid: string, location: string, name: string) {
  return useQuery({
    queryKey: agentUnmanagedSkillFilesKey(agentUid, location, name),
    queryFn: async () => (await agentsApi.unmanagedSkillFiles(agentUid, name, location)).root,
    enabled: !!agentUid && !!location && !!name,
  });
}

export function useUnmanagedSkillFileContent(
  agentUid: string,
  location: string,
  name: string,
  path: string | null,
) {
  return useQuery({
    queryKey: agentUnmanagedSkillFileKey(agentUid, location, name, path ?? ""),
    queryFn: () => agentsApi.unmanagedSkillFileContent(agentUid, name, location, path as string),
    enabled: !!agentUid && !!location && !!name && !!path,
  });
}
