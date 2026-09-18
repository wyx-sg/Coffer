// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
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

export function useAgent(uid: string) {
  return useQuery({
    queryKey: agentKey(uid),
    queryFn: () => agentsApi.get(uid),
    enabled: !!uid,
  });
}

// No onError toast on register / patch: the add dialog and the edit form each
// render the failure inline next to the field it concerns (e.g. the 409 for an
// already-registered config dir), so a toast would double-surface it.
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
    mutationFn: (vars: { uid: string; body: AgentPatch }) => agentsApi.patch(vars.uid, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentsKey });
    },
  });
}

export function useRemoveAgent() {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: (uid: string) => agentsApi.remove(uid),
    onSuccess: (_data, uid) => {
      qc.removeQueries({ queryKey: agentKey(uid) });
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

export function useAgentConfigFiles(uid: string) {
  return useQuery({
    queryKey: agentConfigFilesKey(uid),
    queryFn: async () => (await agentsApi.listConfigFiles(uid)).items,
    enabled: !!uid,
  });
}

export function useAgentConfigFile(uid: string, key: string | null) {
  return useQuery({
    queryKey: agentConfigFileKey(uid, key ?? ""),
    queryFn: () => agentsApi.readConfigFile(uid, key as string),
    enabled: !!uid && !!key,
  });
}

// --- Coffer MCP install (spec agent-registry v2) ---

export function useAgentMcpStatus(uid: string) {
  return useQuery({
    queryKey: agentMcpInstallKey(uid),
    queryFn: () => agentsApi.mcpStatus(uid),
    enabled: !!uid,
  });
}

export function useAgentMcpInstall(uid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: (install: boolean) =>
      install ? agentsApi.mcpInstall(uid) : agentsApi.mcpUninstall(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentMcpInstallKey(uid) });
    },
    onError,
  });
}

// --- MCP entries (specs agent-registry/skill-manager workspace amendment) ---

export function useAgentMcpEntries(uid: string) {
  return useQuery({
    queryKey: agentMcpEntriesKey(uid),
    queryFn: () => agentsApi.mcpEntries(uid),
    enabled: !!uid,
  });
}

export function useRemoveMcpEntry(agentUid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ entry, source }: { entry: string; source?: string }) =>
      agentsApi.removeMcpEntry(agentUid, entry, source),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentMcpEntriesKey(agentUid) });
    },
    onError,
  });
}

// No onError toast: the adopt dialog shows the failure inline, where the
// name-conflict / secret hints it carries are actionable.
export function useAdoptMcpEntry(agentUid: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, body }: { entry: string; body: AdoptMcpEntryBody }) =>
      agentsApi.adoptMcpEntry(agentUid, entry, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentMcpEntriesKey(agentUid) });
      qc.invalidateQueries({ queryKey: resourcesByKindKey("mcp_server") });
    },
  });
}

// --- Plugins (spec agent-registry, workspace amendment) ---

export function useAgentPlugins(uid: string) {
  return useQuery({
    queryKey: agentPluginsKey(uid),
    queryFn: () => agentsApi.plugins(uid),
    enabled: !!uid,
  });
}

export function useTogglePlugin(agentUid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      agentsApi.togglePlugin(agentUid, id, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentPluginsKey(agentUid) });
    },
    onError,
  });
}

export function useUninstallPlugin(agentUid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => agentsApi.uninstallPlugin(agentUid, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentPluginsKey(agentUid) });
    },
    onError,
  });
}

// --- Config-file children (specs agent-registry/skill-manager workspace amendment) — read-only ---

export function useAgentConfigChild(uid: string, key: string, relpath: string) {
  return useQuery({
    queryKey: agentConfigChildKey(uid, key, relpath),
    queryFn: () => agentsApi.readConfigChild(uid, key, relpath),
    enabled: !!uid && !!key && !!relpath,
  });
}

// --- Unmanaged skills (specs agent-registry/skill-manager workspace amendment) ---

export function useUnmanagedSkills(uid: string) {
  return useQuery({
    queryKey: agentUnmanagedSkillsKey(uid),
    queryFn: () => agentsApi.unmanagedSkills(uid),
    enabled: !!uid,
  });
}

/** Invalidate what adopting or deleting an unmanaged skill changes: the
 *  unmanaged list, the managed skills list it may now appear in, and the
 *  agent itself (its skill counts). */
function invalidateUnmanagedSkills(qc: ReturnType<typeof useQueryClient>, agentUid: string) {
  qc.invalidateQueries({ queryKey: agentUnmanagedSkillsKey(agentUid) });
  qc.invalidateQueries({ queryKey: skillsKey });
  qc.invalidateQueries({ queryKey: agentKey(agentUid) });
}

export function useAdoptUnmanagedSkill(agentUid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.adoptUnmanagedSkill(agentUid, skill, location),
    onSuccess: () => invalidateUnmanagedSkills(qc, agentUid),
    onError,
  });
}

export function useDeleteUnmanagedSkill(agentUid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.deleteUnmanagedSkill(agentUid, skill, location),
    onSuccess: () => invalidateUnmanagedSkills(qc, agentUid),
    onError,
  });
}
