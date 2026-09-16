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

export function useAgentNativeMemory(name: string) {
  return useQuery({
    queryKey: agentNativeMemoryKey(name),
    queryFn: () => agentNativeMemoryApi.list(name),
    enabled: !!name,
  });
}

const nativeMemoryFilesKey = (name: string, dir: string) =>
  ["agents", name, "native-memory", dir, "files"] as const;

const nativeMemoryFileKey = (name: string, dir: string, path: string) =>
  ["agents", name, "native-memory", dir, "files", path] as const;

export function useNativeMemoryFiles(name: string, dir: string) {
  return useQuery({
    queryKey: nativeMemoryFilesKey(name, dir),
    queryFn: () => agentNativeMemoryApi.files(name, dir),
    enabled: !!name && !!dir,
  });
}

export function useNativeMemoryFileContent(name: string, dir: string, path: string) {
  return useQuery({
    queryKey: nativeMemoryFileKey(name, dir, path),
    queryFn: () => agentNativeMemoryApi.fileContent(name, dir, path),
    enabled: !!name && !!dir && !!path,
  });
}
