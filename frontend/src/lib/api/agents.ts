// frontend/src/lib/api/agents.ts — typed fetch helpers for /api/v1/agents/*
// Until openapi codegen merges specs 003/004, we hand-write the wire types
// to match `specs/004-agent-registry/contracts/api.openapi.yaml`.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// The backend supports exactly two agent types (Claude Code, Codex); keep this
// union in sync with `AgentType` in the backend domain (`domain/agent/types.py`).
export type AgentType = "claude_code" | "codex";

export type ConfigFileFormat = "json" | "toml" | "markdown" | "text";

export interface ConfigFileInfo {
  key: string;
  display_name: string;
  path: string;
  /** Absolute path of the containing folder (for the "open folder" affordance). */
  folder_path?: string;
  format: ConfigFileFormat;
  exists: boolean;
  size: number | null;
  modified_at: string | null;
  kind?: string;
  files?: { relpath: string; size: number; modified_at: string }[] | null;
}

export interface ConfigFileListOut {
  items: ConfigFileInfo[];
}

export interface ConfigFileContent {
  key: string;
  format: ConfigFileFormat;
  exists: boolean;
  content: string;
  /** Absolute path of the file being viewed (for the external-editor actions). */
  path?: string;
  /** Absolute path of its containing folder. */
  folder_path?: string;
  fingerprint?: string;
  memory_block?: boolean;
}

export interface McpInstallStatus {
  installed: boolean;
  command: string | null;
}

export interface AgentOut {
  name: string;
  type: AgentType;
  config_dir: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  follow_all_skills?: boolean;
  skill_exclusions?: string[];
}

export interface AgentListOut {
  items: AgentOut[];
}

export interface AgentCreate {
  type: AgentType;
  // Optional — the server derives a stable default from the type when omitted.
  name?: string | null;
  // Optional override; default is the type's standard config directory.
  config_dir?: string | null;
  description?: string | null;
}

export interface AgentPatch {
  config_dir?: string | null;
  description?: string | null;
  follow_all_skills?: boolean;
  skill_exclusions?: string[];
}

export interface AgentCandidate {
  type: AgentType;
  display_name: string;
  config_dir: string;
  default_skill_dir: string;
  suggested_name: string;
}

export interface AgentCandidatesOut {
  candidates: AgentCandidate[];
}

export interface McpEntryOut {
  name: string;
  source: string;
  transport: "stdio" | "http";
  command: string | null;
  args: string[];
  env_keys: string[];
  secret_keys: string[];
  url: string | null;
  header_keys: string[];
  enabled: boolean | null;
  is_coffer: boolean;
  matches_resource: string | null;
}

export interface McpEntriesResponse {
  items: McpEntryOut[];
  parse_errors: { source: string; path: string; error: string }[];
}

export interface AdoptMcpEntryBody {
  source?: string;
  new_name?: string;
  secrets?: Record<string, string>;
}

export interface PluginOut {
  id: string;
  name: string;
  marketplace: string;
  enabled: boolean;
  cache_present: boolean;
  // Best-effort detail read from the plugin's install dir (Claude only today;
  // null / empty otherwise).
  version?: string | null;
  description?: string | null;
  author?: string | null;
  homepage?: string | null;
  skills?: string[];
  commands?: string[];
  mcp_servers?: string[];
}

export interface MarketplaceOut {
  name: string;
  source_type: string | null;
  source: string | null;
}

export interface PluginsResponse {
  items: PluginOut[];
  marketplaces: MarketplaceOut[];
  parse_errors: unknown[];
  // Whether in-app uninstall is available for this agent now (capability +, for
  // CLI-strategy agents like Claude, the agent's CLI being on PATH).
  can_uninstall?: boolean;
}

export interface UnmanagedSkillOut {
  name: string;
  path: string;
  location: string;
  valid: boolean;
  reason: string | null;
  foreign_link: boolean;
}

export interface UnmanagedSkillsResponse {
  items: UnmanagedSkillOut[];
}

export async function call<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) {
    return undefined as unknown as T;
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
      err?.details,
    );
  }
  return data as T;
}

// Agent names and config-file keys are interpolated into URL paths; encode them
// so a name/key with URL-significant characters can't malform or misroute the
// request (defence in depth — the daemon also constrains names server-side).
export const enc = encodeURIComponent;

export const agentsApi = {
  list: () => call<AgentListOut>("GET", "/agents"),
  register: (body: AgentCreate) => call<AgentOut>("POST", "/agents", body),
  get: (name: string) => call<AgentOut>("GET", `/agents/${enc(name)}`),
  patch: (name: string, body: AgentPatch) => call<AgentOut>("PATCH", `/agents/${enc(name)}`, body),
  remove: (name: string) => call<void>("DELETE", `/agents/${enc(name)}`),
  // Read-only discovery: installed-but-unregistered agents the user can add.
  candidates: () => call<AgentCandidatesOut>("GET", "/agents/candidates"),

  // Config files are read-only in the UI: viewing happens in-app, editing in the
  // user's own editor (the write endpoint still exists server-side, but the UI
  // no longer calls it).
  listConfigFiles: (name: string) =>
    call<ConfigFileListOut>("GET", `/agents/${enc(name)}/config-files`),
  readConfigFile: (name: string, key: string) =>
    call<ConfigFileContent>("GET", `/agents/${enc(name)}/config-files/${enc(key)}`),

  mcpStatus: (name: string) => call<McpInstallStatus>("GET", `/agents/${enc(name)}/mcp-install`),
  mcpInstall: (name: string) => call<McpInstallStatus>("POST", `/agents/${enc(name)}/mcp-install`),
  mcpUninstall: (name: string) =>
    call<McpInstallStatus>("DELETE", `/agents/${enc(name)}/mcp-install`),

  // MCP entries (specs 004/005 workspace amendment)
  mcpEntries: (name: string) => call<McpEntriesResponse>("GET", `/agents/${enc(name)}/mcp-entries`),
  toggleMcpEntry: (name: string, entry: string, enabled: boolean) =>
    call<void>("PATCH", `/agents/${enc(name)}/mcp-entries/${enc(entry)}`, { enabled }),
  removeMcpEntry: (name: string, entry: string, source?: string) => {
    const qs = source ? `?source=${encodeURIComponent(source)}` : "";
    return call<void>("DELETE", `/agents/${enc(name)}/mcp-entries/${enc(entry)}${qs}`);
  },
  adoptMcpEntry: (name: string, entry: string, body: AdoptMcpEntryBody) =>
    call<{ kind: string; name: string }>(
      "POST",
      `/agents/${enc(name)}/mcp-entries/${enc(entry)}/adopt`,
      body,
    ),

  // Plugins (specs 004/005 workspace amendment)
  plugins: (name: string) => call<PluginsResponse>("GET", `/agents/${enc(name)}/plugins`),
  togglePlugin: (name: string, id: string, enabled: boolean) =>
    call<void>("PATCH", `/agents/${enc(name)}/plugins/${encodeURIComponent(id)}`, { enabled }),
  uninstallPlugin: (name: string, id: string) =>
    call<void>("DELETE", `/agents/${enc(name)}/plugins/${encodeURIComponent(id)}`),

  // Config-file child (per-file inside a directory-backed config key) — read-only.
  readConfigChild: (name: string, key: string, relpath: string) => {
    const encodedRelpath = relpath.split("/").map(encodeURIComponent).join("/");
    return call<ConfigFileContent>(
      "GET",
      `/agents/${enc(name)}/config-files/${enc(key)}/files/${encodedRelpath}`,
    );
  },

  // Unmanaged skills (specs 004/005 workspace amendment)
  unmanagedSkills: (name: string) =>
    call<UnmanagedSkillsResponse>("GET", `/agents/${enc(name)}/unmanaged-skills`),
  adoptUnmanagedSkill: (name: string, skill: string, location: string) =>
    call<{ name: string }>("POST", `/agents/${enc(name)}/unmanaged-skills/${enc(skill)}/adopt`, {
      location,
    }),
  deleteUnmanagedSkill: (name: string, skill: string, location: string) =>
    call<void>(
      "DELETE",
      `/agents/${enc(name)}/unmanaged-skills/${enc(skill)}?location=${encodeURIComponent(location)}`,
    ),
};
