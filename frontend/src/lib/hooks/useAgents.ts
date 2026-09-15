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

const AGENTS_KEY = ["agents"] as const;

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useAgentToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

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

// No onError toast on register / patch: the add dialog and the edit form each
// render the failure inline next to the field it concerns (e.g. the 409 for an
// already-registered config dir), so a toast would double-surface it.
export function useRegisterAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => agentsApi.register(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function usePatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: AgentPatch }) => agentsApi.patch(vars.name, vars.body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
  });
}

export function useRemoveAgent() {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: (name: string) => agentsApi.remove(name),
    onSuccess: (_data, name) => {
      qc.removeQueries({ queryKey: ["agents", name] });
      void qc.invalidateQueries({ queryKey: AGENTS_KEY });
    },
    onError,
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

// --- config files (spec agent-registry v2) ---

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

// --- Coffer MCP install (spec agent-registry v2) ---

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
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: (install: boolean) =>
      install ? agentsApi.mcpInstall(name) : agentsApi.mcpUninstall(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: mcpKey(name) });
    },
    onError,
  });
}

// --- MCP entries (specs agent-registry/skill-manager workspace amendment) ---

export function useAgentMcpEntries(name: string) {
  return useQuery({
    queryKey: ["agents", name, "mcp-entries"],
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
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "mcp-entries"] });
    },
    onError,
  });
}

// No onError toast: the adopt dialog shows the failure inline, where the
// name-conflict / secret hints it carries are actionable.
export function useAdoptMcpEntry(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entry, body }: { entry: string; body: AdoptMcpEntryBody }) =>
      agentsApi.adoptMcpEntry(agentName, entry, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "mcp-entries"] });
      void qc.invalidateQueries({ queryKey: ["resources", { kind: "mcp_server" }] });
    },
  });
}

// --- Plugins (spec agent-registry, workspace amendment) ---

export function useAgentPlugins(name: string) {
  return useQuery({
    queryKey: ["agents", name, "plugins"],
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
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "plugins"] });
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
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "plugins"] });
    },
    onError,
  });
}

// --- Config-file children (specs agent-registry/skill-manager workspace amendment) — read-only ---

export function useAgentConfigChild(name: string, key: string, relpath: string) {
  return useQuery({
    queryKey: ["agents", name, "config-files", key, relpath],
    queryFn: () => agentsApi.readConfigChild(name, key, relpath),
    enabled: !!name && !!key && !!relpath,
  });
}

// --- Unmanaged skills (specs agent-registry/skill-manager workspace amendment) ---

export function useUnmanagedSkills(name: string) {
  return useQuery({
    queryKey: ["agents", name, "unmanaged-skills"],
    queryFn: () => agentsApi.unmanagedSkills(name),
    enabled: !!name,
  });
}

export function useAdoptUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.adoptUnmanagedSkill(agentName, skill, location),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "unmanaged-skills"] });
      void qc.invalidateQueries({ queryKey: ["skills"] });
      void qc.invalidateQueries({ queryKey: ["agents", agentName] });
    },
    onError,
  });
}

export function useDeleteUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  const onError = useAgentToastError();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.deleteUnmanagedSkill(agentName, skill, location),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agents", agentName, "unmanaged-skills"] });
      void qc.invalidateQueries({ queryKey: ["skills"] });
      void qc.invalidateQueries({ queryKey: ["agents", agentName] });
    },
    onError,
  });
}
