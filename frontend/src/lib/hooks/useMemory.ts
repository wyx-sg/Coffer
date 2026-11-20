// frontend/src/lib/hooks/useMemory.ts
//
// ALL queries + mutations for memory (agents/frontend.md §3; spec memory "Show
// and edit memory on the Memory page"). Keys are hierarchical under one
// `["memory"]` root, so an edit or a delete — which can change a project's
// counts and its list — invalidates the whole subtree with one prefix. While a
// tidy is open the state is re-read, so the page sees it close.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteMemoryFile,
  getMemoryFile,
  getMemoryState,
  listTopics,
  saveMemoryFile,
} from "@/lib/api/memory";
import { memoryFileKey, memoryKey, memoryStateKey, memoryTopicsKey } from "@/lib/api/queryKeys";

/** How often the state is re-read while an agent's tidy is open. */
const POLL_WHILE_TIDYING_MS = 5000;

export function useMemoryState() {
  return useQuery({
    queryKey: memoryStateKey,
    queryFn: getMemoryState,
    refetchInterval: (query) => (query.state.data?.tidy_running ? POLL_WHILE_TIDYING_MS : false),
  });
}

/** One project's topic files; `null` reads nothing. */
export function useMemoryTopics(project: string | null) {
  return useQuery({
    queryKey: memoryTopicsKey(project ?? ""),
    queryFn: () => listTopics(project ?? ""),
    enabled: project !== null,
  });
}

/** One topic file's text and digest; `null` reads nothing. */
export function useMemoryFile(project: string | null, name: string | null) {
  return useQuery({
    queryKey: memoryFileKey(project ?? "", name ?? ""),
    queryFn: () => getMemoryFile(project ?? "", name ?? ""),
    enabled: project !== null && name !== null,
  });
}

/** Save a person's edit. No `onError` toast: the edit dialog stays open and shows it. */
export function useSaveMemoryFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { project: string; name: string; text: string; expected: string }) =>
      saveMemoryFile(v.project, v.name, v.text, v.expected),
    onSuccess: () => void qc.invalidateQueries({ queryKey: memoryKey }),
  });
}

/** Delete a file. No `onError` toast: the confirm dialog stays open and shows it. */
export function useDeleteMemoryFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { project: string; name: string; expected: string }) =>
      deleteMemoryFile(v.project, v.name, v.expected),
    onSuccess: () => void qc.invalidateQueries({ queryKey: memoryKey }),
  });
}
