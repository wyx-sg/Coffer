// frontend/src/lib/hooks/useAgentNativeMemory.ts — TanStack Query bindings for
// the agent's OWN native memory stores: the listing, one store's file tree, and
// one file's contents. Read-only throughout — no mutations, so there is nothing
// to invalidate. Every key extends the agent's own key so deleting or refetching
// an agent sweeps this whole subtree with it, and the store-level keys carry the
// `memory_dir` because that is a store's identity (for Codex, several listed
// rows share one directory and must therefore share one cache entry).
import { useQuery } from "@tanstack/react-query";

import { agentNativeMemoryApi } from "@/lib/api/agentNativeMemory";
import { agentNativeMemoryKey } from "@/lib/api/queryKeys";

export function useAgentNativeMemory(agentUid: string) {
  return useQuery({
    queryKey: agentNativeMemoryKey(agentUid),
    queryFn: () => agentNativeMemoryApi.list(agentUid),
    enabled: !!agentUid,
  });
}

const nativeMemoryFilesKey = (agentUid: string, dir: string) =>
  ["agents", agentUid, "native-memory", dir, "files"] as const;

const nativeMemoryFileKey = (agentUid: string, dir: string, path: string) =>
  ["agents", agentUid, "native-memory", dir, "files", path] as const;

export function useNativeMemoryFiles(agentUid: string, dir: string) {
  return useQuery({
    queryKey: nativeMemoryFilesKey(agentUid, dir),
    queryFn: () => agentNativeMemoryApi.files(agentUid, dir),
    enabled: !!agentUid && !!dir,
  });
}

export function useNativeMemoryFileContent(agentUid: string, dir: string, path: string) {
  return useQuery({
    queryKey: nativeMemoryFileKey(agentUid, dir, path),
    queryFn: () => agentNativeMemoryApi.fileContent(agentUid, dir, path),
    enabled: !!agentUid && !!dir && !!path,
  });
}
