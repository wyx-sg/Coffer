// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { agentsApi, type AgentCreate, type AgentPatch } from "@/lib/api/agents";
import type { AdoptMcpEntryBody, AdoptSkillVars } from "@/lib/api/agents-workspace";
import { translateApiError } from "@/lib/api/errors";
import {
  agentTypesKey,
  agentConfigChildKey,
  agentConfigFileKey,
  agentConfigFilesKey,
  agentHooksKey,
  agentPluginKey,
  agentPluginsKey,
  agentKey,
  agentMcpEntriesKey,
  agentConnectionKey,
  agentMcpEntryKey,
  agentsKey,
  agentUnmanagedSkillsKey,
  resourcesByKindKey,
  skillsKey,
} from "@/lib/api/queryKeys";

/** Shared onError → toast handler — a failed mutation must never be silent.
 *  Mutations whose consumer already renders the translated error inline
 *  (register, patch, coffer-connection, adopt-mcp-entry) or toasts at the call site
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
export const AGENT_REGISTER_KEY = ["agent", "register"] as const;
export const agentConnectMutationKey = (uid: string) => ["agent", "connect", uid] as const;

export function useRegisterAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: AGENT_REGISTER_KEY,
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

/** Every supported type with its detection state and — when added — its uid:
 *  the Agents page's two fixed rows and the type → uid step of every page
 *  under /agents/:type. Detection is automatic (spec agent-registry "Expose
 *  agent discovery on every surface"): read on load, when the window regains
 *  focus, and every few minutes, never behind a Detect action. */
export function useAgentTypes() {
  return useQuery({
    queryKey: agentTypesKey,
    queryFn: async () => (await agentsApi.types()).types,
    refetchOnWindowFocus: true,
    refetchInterval: 3 * 60_000,
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

// --- Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") ---

export function useAgentConnection(uid: string) {
  return useQuery({
    queryKey: agentConnectionKey(uid),
    queryFn: () => agentsApi.connection(uid),
    enabled: !!uid,
  });
}

/** `true` connects (installs every applicable part), `false` disconnects. */
export function useAgentConnect(uid: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationKey: agentConnectMutationKey(uid),
    mutationFn: (connect: boolean) =>
      connect ? agentsApi.connect(uid) : agentsApi.disconnect(uid),
    onSuccess: (data) => {
      qc.setQueryData(agentConnectionKey(uid), data);
      // Connecting (re)installs Coffer's hook, whose health the Hooks tab shows.
      void qc.invalidateQueries({ queryKey: agentHooksKey(uid) });
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

/** One direct entry in full, for its detail page. `source` may be empty when
 *  the URL carried none — the daemon then resolves the name on its own. */
export function useAgentMcpEntry(uid: string, entry: string, source: string) {
  return useQuery({
    queryKey: agentMcpEntryKey(uid, entry, source),
    queryFn: () => agentsApi.mcpEntry(uid, entry, source || undefined),
    enabled: !!uid && !!entry,
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

// --- Hooks (spec agent-registry "List every hook in the agent's native config") — read-only ---

export function useAgentHooks(uid: string) {
  return useQuery({
    queryKey: agentHooksKey(uid),
    queryFn: () => agentsApi.hooks(uid),
    enabled: !!uid,
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

export function useAgentPlugin(uid: string, id: string) {
  return useQuery({
    queryKey: agentPluginKey(uid, id),
    queryFn: () => agentsApi.plugin(uid, id),
    enabled: !!uid && !!id,
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

export function useAdoptUnmanagedSkill(agentUid: string, { toastErrors = true } = {}) {
  const qc = useQueryClient();
  const toastError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location, ...options }: AdoptSkillVars) =>
      agentsApi.adoptUnmanagedSkill(agentUid, skill, location, options),
    onSuccess: () => invalidateUnmanagedSkills(qc, agentUid),
    // A dialog that shows the failure itself turns the toast off.
    onError: toastErrors ? toastError : undefined,
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
