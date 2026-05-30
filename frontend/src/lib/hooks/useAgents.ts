// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { agentsApi, type AgentCreate, type AgentPatch } from "@/lib/api/agents";

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

// Read-only discovery of installed-but-unregistered agents (candidates). The
// query is gated on `enabled` so it only scans while the detect dialog is open.
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

// Save (atomic write + `.bak`). On success, refetch both the per-file content
// query (key/size/mtime change) and the list query (existence/size metadata).
export function useSaveAgentConfigFile(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { key: string; content: string }) =>
      agentsApi.writeConfigFile(name, vars.key, vars.content),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: configFileKey(name, vars.key) });
      qc.invalidateQueries({ queryKey: configFilesKey(name) });
    },
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
