// src/lib/hooks/useConfigDirFiles.ts — create and delete a file inside a Config files directory entry (boards 2.1.57, 2.1.58).
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { agentsApi } from "@/lib/api/agents";
import { agentConfigChildKey, agentConfigFilesKey } from "@/lib/api/queryKeys";

interface Target {
  key: string;
  relpath: string;
}

export function useCreateConfigChild(agentUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, relpath, content }: Target & { content: string }) =>
      agentsApi.writeConfigChild(agentUid, key, relpath, { content }),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentConfigFilesKey(agentUid) }),
  });
}

export function useDeleteConfigChild(agentUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, relpath }: Target) => agentsApi.deleteConfigChild(agentUid, key, relpath),
    onSuccess: (_void, { key, relpath }) => {
      qc.removeQueries({ queryKey: agentConfigChildKey(agentUid, key, relpath) });
      return qc.invalidateQueries({ queryKey: agentConfigFilesKey(agentUid) });
    },
  });
}
