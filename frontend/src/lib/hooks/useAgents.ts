// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  agentsApi,
  type AdoptMcpEntryBody,
  type AgentCreate,
  type AgentPatch,
  type NativeMemoryListResponse,
} from "@/lib/api/agents";

const AGENTS_KEY = ["agents"] as const;

export function useAgents() {
  return useQuery({
    queryKey: AGENTS_KEY,
    queryFn: async () => (await agentsApi.list()).items,
  });
}

export function useAgent(name: string) {
  return useQuery({
    queryKey: ["agents", name],
    queryFn: () => agentsApi.get(name),
    enabled: !!name,
  });
}

export function useRegisterAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.register(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function usePatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: AgentPatch }) => agentsApi.patch(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function useRemoveAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => agentsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

// Read-only discovery of installed-but-unregistered agents; gated on `enabled`.
export function useAgentCandidates(enabled: boolean) {
  return useQuery({
    queryKey: ["agents", "candidates"],
    queryFn: async () => (await agentsApi.candidates()).candidates,
    enabled,
  });
}

// --- config files (spec 004 v2) ---

const configFilesKey = (name: string) => ["agents", name, "config-files"] as const;
const configFileKey = (name: string, key: string) => ["agents", name, "config-files", key] as const;

export function useAgentConfigFiles(name: string) {
  return useQuery({
    queryKey: configFilesKey(name),
    queryFn: async () => (await agentsApi.listConfigFiles(name)).items,
    enabled: !!name,
  });
}

export function useAgentConfigFile(name: string, key: string | null) {
  return useQuery({
    queryKey: configFileKey(name, key ?? ""),
    queryFn: () => agentsApi.readConfigFile(name, key as string),
    enabled: !!name && !!key,
  });
}

// --- Coffer MCP install (spec 004 v2) ---

const mcpKey = (name: string) => ["agents", name, "mcp-install"] as const;

export function useAgentMcpStatus(name: string) {
  return useQuery({
    queryKey: mcpKey(name),
    queryFn: () => agentsApi.mcpStatus(name),
    enabled: !!name,
  });
}

export function useAgentMcpInstall(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (install: boolean) =>
      install ? agentsApi.mcpInstall(name) : agentsApi.mcpUninstall(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: mcpKey(name) });
    },
  });
}

// --- Session-start hook install (rules injection, slice 6) ---

const hookKey = (name: string) => ["agents", name, "hook-install"] as const;

export function useAgentHookStatus(name: string) {
  return useQuery({
    queryKey: hookKey(name),
    queryFn: () => agentsApi.hookStatus(name),
    enabled: !!name,
    // A 422 HOOK_INSTALL_UNSUPPORTED is a stable signal, not transient — don't retry.
    retry: false,
  });
}

export function useAgentHookInstall(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (install: boolean) =>
      install ? agentsApi.hookInstall(name) : agentsApi.hookUninstall(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: hookKey(name) });
    },
  });
}

// --- MCP entries (specs 004/005 workspace amendment) ---

export function useAgentMcpEntries(name: string) {
  return useQuery({
    queryKey: ["agents", name, "mcp-entries"],
    queryFn: () => agentsApi.mcpEntries(name),
    enabled: !!name,
  });
}

export function useToggleMcpEntry(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, enabled }: { entry: string; enabled: boolean }) =>
      agentsApi.toggleMcpEntry(agentName, entry, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "mcp-entries"] });
    },
  });
}

export function useRemoveMcpEntry(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, source }: { entry: string; source?: string }) =>
      agentsApi.removeMcpEntry(agentName, entry, source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "mcp-entries"] });
    },
  });
}

export function useAdoptMcpEntry(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, body }: { entry: string; body: AdoptMcpEntryBody }) =>
      agentsApi.adoptMcpEntry(agentName, entry, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "mcp-entries"] });
      qc.invalidateQueries({ queryKey: ["resources", { kind: "mcp_server" }] });
    },
  });
}

// --- Plugins (specs 004/005 workspace amendment) ---

export function useAgentPlugins(name: string) {
  return useQuery({
    queryKey: ["agents", name, "plugins"],
    queryFn: () => agentsApi.plugins(name),
    enabled: !!name,
  });
}

export function useTogglePlugin(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      agentsApi.togglePlugin(agentName, id, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "plugins"] });
    },
  });
}

export function useUninstallPlugin(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => agentsApi.uninstallPlugin(agentName, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "plugins"] });
    },
  });
}

// --- Config-file children (specs 004/005 workspace amendment) — read-only ---

export function useAgentConfigChild(name: string, key: string, relpath: string) {
  return useQuery({
    queryKey: ["agents", name, "config-files", key, relpath],
    queryFn: () => agentsApi.readConfigChild(name, key, relpath),
    enabled: !!name && !!key && !!relpath,
  });
}

// --- Unmanaged skills (specs 004/005 workspace amendment) ---

export function useUnmanagedSkills(name: string) {
  return useQuery({
    queryKey: ["agents", name, "unmanaged-skills"],
    queryFn: () => agentsApi.unmanagedSkills(name),
    enabled: !!name,
  });
}

// --- Native memory (the agent's OWN per-project memory stores, read-only) ---

const nativeMemoryKey = (name: string) => ["agents", name, "native-memory"] as const;

/** Poll the list (2s) while any store is queued/running; stop once settled. */
function nativeImportRefetch(data: NativeMemoryListResponse | undefined): number | false {
  const busy = (data?.items ?? []).some(
    (s) => s.import_status === "queued" || s.import_status === "running",
  );
  return busy ? 2000 : false;
}

export function useAgentNativeMemory(name: string) {
  return useQuery({
    queryKey: nativeMemoryKey(name),
    queryFn: () => agentsApi.nativeMemory(name),
    enabled: !!name,
    refetchInterval: (query) => nativeImportRefetch(query.state.data),
  });
}

/** Enqueue async batch import for native-memory stores (returns at once). */
export function useImportNativeMemoryBatch(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memoryDirs: string[]) => agentsApi.importNativeMemoryBatch(agentName, memoryDirs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: nativeMemoryKey(agentName) });
      qc.invalidateQueries({ queryKey: ["memory-stores"] });
    },
  });
}

export function useAdoptUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.adoptUnmanagedSkill(agentName, skill, location),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "unmanaged-skills"] });
      qc.invalidateQueries({ queryKey: ["skills"] });
      qc.invalidateQueries({ queryKey: ["agents", agentName] });
    },
  });
}

export function useDeleteUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.deleteUnmanagedSkill(agentName, skill, location),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "unmanaged-skills"] });
      qc.invalidateQueries({ queryKey: ["skills"] });
      qc.invalidateQueries({ queryKey: ["agents", agentName] });
    },
  });
}
