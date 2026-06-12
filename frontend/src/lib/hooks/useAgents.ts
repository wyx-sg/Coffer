// frontend/src/lib/hooks/useAgents.ts — TanStack Query bindings for agents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  agentsApi,
  type AdoptMcpEntryBody,
  type AgentCreate,
  type AgentPatch,
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
// `expected_fingerprint` (when the content query supplied one) makes the
// server reject the write with 409 CONFIG_FILE_STALE if the file changed on
// disk since it was read.
export function useSaveAgentConfigFile(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { key: string; content: string; expected_fingerprint?: string }) =>
      agentsApi.writeConfigFile(name, vars.key, {
        content: vars.content,
        expected_fingerprint: vars.expected_fingerprint,
      }),
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
      // Invalidate resources for the mcp_server kind (matches useResources.ts key shape)
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

// --- Config-file children (specs 004/005 workspace amendment) ---

export function useAgentConfigChild(name: string, key: string, relpath: string) {
  return useQuery({
    queryKey: ["agents", name, "config-files", key, relpath],
    queryFn: () => agentsApi.readConfigChild(name, key, relpath),
    enabled: !!name && !!key && !!relpath,
  });
}

export function useWriteConfigChild(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      key,
      relpath,
      content,
      expected_fingerprint,
    }: {
      key: string;
      relpath: string;
      content: string;
      expected_fingerprint?: string;
    }) => agentsApi.writeConfigChild(agentName, key, relpath, { content, expected_fingerprint }),
    onSuccess: (_data, { key, relpath }) => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "config-files"] });
      qc.invalidateQueries({ queryKey: ["agents", agentName, "config-files", key, relpath] });
    },
  });
}

export function useDeleteConfigChild(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, relpath }: { key: string; relpath: string }) =>
      agentsApi.deleteConfigChild(agentName, key, relpath),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "config-files"] });
    },
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

export function useAdoptUnmanagedSkill(agentName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ skill, location }: { skill: string; location: string }) =>
      agentsApi.adoptUnmanagedSkill(agentName, skill, location),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents", agentName, "unmanaged-skills"] });
      // Invalidate the global skills list (matches SKILLS_KEY in useSkills.ts)
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
      // Invalidate the global skills list (matches SKILLS_KEY in useSkills.ts)
      qc.invalidateQueries({ queryKey: ["skills"] });
      qc.invalidateQueries({ queryKey: ["agents", agentName] });
    },
  });
}
