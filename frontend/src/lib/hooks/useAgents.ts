// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  agentsApi,
  type AdoptMcpEntryBody,
  type AgentCreate,
  type AgentPatch,
} from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import {
  agentCandidatesKey,
  agentConfigChildKey,
  agentConfigFileKey,
  agentConfigFilesKey,
  agentKey,
  agentMcpEntriesKey,
  agentMcpInstallKey,
  agentPluginsKey,
  agentsKey,
  agentUnmanagedSkillsKey,
  resourcesByKindKey,
  skillsKey,
} from "@/lib/api/queryKeys";
import { useToast } from "@/components/ui/toast";

/** Shared onError → toast handler — a failed mutation must never be silent.
 *  Mutations whose consumer already renders the translated error inline
 *  (register, patch, mcp-install, adopt-mcp-entry) or toasts at the call site
 *  (unmanaged skills) do not use it, so one failure is reported once. */
function useAgentToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useAgents() {
  return useQuery({
    queryKey: agentsKey,
    queryFn: async () => (await agentsApi.list()).items,
  });
}

export function useAgent(name: string) {
  return useQuery({
    queryKey: agentKey(name),
    queryFn: () => agentsApi.get(name),
    enabled: !!name,
  });
}

export function useRegisterAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.register(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentsKey });
    },
  });
}

export function usePatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: AgentPatch }) => agentsApi.patch(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentsKey });
    },
  });
}

export function useRemoveAgent() {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: (name: string) => agentsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentsKey });
    },
    onError,
  });
}

// Read-only discovery of installed-but-unregistered agents; gated on `enabled`.
export function useAgentCandidates(enabled: boolean) {
  return useQuery({
    queryKey: agentCandidatesKey,
    queryFn: async () => (await agentsApi.candidates()).candidates,
    enabled,
  });
}

// --- config files (spec agent-registry v2) ---

export function useAgentConfigFiles(name: string) {
  return useQuery({
    queryKey: agentConfigFilesKey(name),
    queryFn: async () => (await agentsApi.listConfigFiles(name)).items,
    enabled: !!name,
  });
}

export function useAgentConfigFile(name: string, key: string | null) {
  return useQuery({
    queryKey: agentConfigFileKey(name, key ?? ""),
    queryFn: () => agentsApi.readConfigFile(name, key as string),
    enabled: !!name && !!key,
  });
}

// --- Coffer MCP install (spec agent-registry v2) ---

export function useAgentMcpStatus(name: string) {
  return useQuery({
    queryKey: agentMcpInstallKey(name),
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
      qc.invalidateQueries({ queryKey: agentMcpInstallKey(name) });
    },
  });
}

// --- MCP entries (specs agent-registry/skill-manager workspace amendment) ---

export function useAgentMcpEntries(name: string) {
  return useQuery({
    queryKey: agentMcpEntriesKey(name),
    queryFn: () => agentsApi.mcpEntries(name),
    enabled: !!name,
  });
}

export function useRemoveMcpEntry(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ entry, source }: { entry: string; source?: string }) =>
      agentsApi.removeMcpEntry(agentName, entry, source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentMcpEntriesKey(agentName) });
    },
    onError,
  });
}

export function useAdoptMcpEntry(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, body }: { entry: string; body: AdoptMcpEntryBody }) =>
      agentsApi.adoptMcpEntry(agentName, entry, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentMcpEntriesKey(agentName) });
      qc.invalidateQueries({ queryKey: resourcesByKindKey("mcp_server") });
    },
  });
}

// --- Plugins (spec agent-registry, workspace amendment) ---

export function useAgentPlugins(name: string) {
  return useQuery({
    queryKey: agentPluginsKey(name),
    queryFn: () => agentsApi.plugins(name),
    enabled: !!name,
  });
}

export function useTogglePlugin(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      agentsApi.togglePlugin(agentName, id, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentPluginsKey(agentName) });
    },
    onError,
  });
}

export function useUninstallPlugin(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => agentsApi.uninstallPlugin(agentName, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentPluginsKey(agentName) });
    },
    onError,
  });
}

// --- Config-file children (specs agent-registry/skill-manager workspace amendment) — read-only ---

export function useAgentConfigChild(name: string, key: string, relpath: string) {
  return useQuery({
    queryKey: agentConfigChildKey(name, key, relpath),
    queryFn: () => agentsApi.readConfigChild(name, key, relpath),
    enabled: !!name && !!key && !!relpath,
  });
}

// --- Unmanaged skills (specs agent-registry/skill-manager workspace amendment) ---

export function useUnmanagedSkills(name: string) {
  return useQuery({
    queryKey: agentUnmanagedSkillsKey(name),
    queryFn: () => agentsApi.unmanagedSkills(name),
    enabled: !!name,
  });
}

/** Invalidate what adopting or deleting an unmanaged skill changes: the
 *  unmanaged list, the managed skills list it may now appear in, and the
 *  agent itself (its skill counts). */
function invalidateUnmanagedSkills(qc: ReturnType<typeof useQueryClient>, agentName: string) {
  qc.invalidateQueries({ queryKey: agentUnmanagedSkillsKey(agentName) });
  qc.invalidateQueries({ queryKey: skillsKey });
  qc.invalidateQueries({ queryKey: agentKey(agentName) });
}

export function useAdoptUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.adoptUnmanagedSkill(agentName, skill, location),
    onSuccess: () => invalidateUnmanagedSkills(qc, agentName),
    onError,
  });
}

export function useDeleteUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.deleteUnmanagedSkill(agentName, skill, location),
    onSuccess: () => invalidateUnmanagedSkills(qc, agentName),
    onError,
  });
}
