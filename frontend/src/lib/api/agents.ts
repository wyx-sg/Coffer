// frontend/src/lib/api/agents.ts — request helpers for /api/v1/agents/*
//
// Wire types are the agent-registry contract's generated schemas
// (`specs/agent-registry/contracts/api.openapi.yaml` → `generated/agent-registry.ts`),
// re-exported under the names the hooks and pages already import. Transport is
// the shared `call` (agents/frontend.md §4).
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/agent-registry";

type Schemas = components["schemas"];

// Keep AgentType in sync with the backend domain (`domain/agent/types.py`).
export type AgentType = Schemas["AgentType"];

type ConfigFileFormat = Schemas["ConfigFileFormat"];

/**
 * Hand-written rather than the contract's `ConfigFileInfo`: the contract makes
 * `folder_path` and `kind` required and `size` / `modified_at` optional; the
 * daemon (and the test fixtures) do the reverse.
 */
export interface ConfigFileInfo {
  key: string;
  display_name: string;
  path: string;
  /** Absolute path of the containing folder. */
  folder_path?: string;
  format: ConfigFileFormat;
  exists: boolean;
  size: number | null;
  modified_at: string | null;
  kind?: Schemas["ConfigFileKind"];
  files?: Schemas["DirChild"][] | null;
}

/** `GET /agents/{name}/config-files` — an inline shape in the contract. */
export interface ConfigFileListOut {
  items: ConfigFileInfo[];
}

/** Body of a config-file save. `expected_fingerprint` makes the write
 *  conditional: the daemon refuses it with 409 CONFIG_FILE_STALE when the file
 *  changed on disk since the read that produced the fingerprint. */
export type ConfigFileWrite = Schemas["ConfigFileWrite"];

/** `path` / `folder_path` are absolute, for the external-editor actions. */
export type ConfigFileContent = Schemas["ConfigFileContent"];

export type McpInstallStatus = Schemas["McpInstallStatus"];

/**
 * Hand-written rather than the contract's `AgentOut`: the contract requires
 * `model` / `fast_model` / `wire_api` and makes `description` optional; the
 * pages and fixtures treat the binding as optional and `description` as
 * always present.
 */
export interface AgentOut {
  name: string;
  type: AgentType;
  config_dir: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  /** Per-agent model binding (spec provider-switching amendment 2026-06-22b). The model the
   * agent projects — null = unbound (falls back to the active connection). */
  model?: string | null;
  fast_model?: string | null;
  wire_api?: string | null;
}

/** `GET /agents` — an inline shape in the contract. */
export interface AgentListOut {
  items: AgentOut[];
}

/**
 * Hand-written rather than the contract's `AgentCreate` / `AgentPatch`: the
 * forms send an explicit `null` for `name` / `config_dir` ("use the default"),
 * which the contract types as `string` only.
 */
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
  // Per-agent model binding (E3); explicit null fast_model clears the fast slot.
  model?: string | null;
  fast_model?: string | null;
  wire_api?: string | null;
}

export type AgentCandidatesOut = Schemas["AgentCandidatesOut"];

// Agent workspace wire types (MCP entries / plugins / unmanaged skills) live in
// agents-workspace.ts for the file-size budget; re-exported so existing
// `from "@/lib/api/agents"` import paths keep working.
export type {
  AdoptMcpEntryBody,
  McpEntriesResponse,
  McpEntryOut,
  PluginOut,
  PluginsResponse,
  UnmanagedSkillOut,
  UnmanagedSkillsResponse,
} from "./agents-workspace";
import type {
  AdoptMcpEntryBody,
  McpEntriesResponse,
  PluginsResponse,
  UnmanagedSkillsResponse,
} from "./agents-workspace";

// A directory-entry child is addressed by a POSIX relpath, so each SEGMENT is
// encoded but the separators are kept — `enc` would escape the slashes and the
// daemon would see one flat name instead of a path.
const childPath = (relpath: string) => relpath.split("/").map(enc).join("/");

export const agentsApi = {
  list: () => call<AgentListOut>("/agents"),
  register: (body: AgentCreate) => call<AgentOut>("/agents", { method: "POST", body }),
  get: (name: string) => call<AgentOut>(`/agents/${enc(name)}`),
  patch: (name: string, body: AgentPatch) =>
    call<AgentOut>(`/agents/${enc(name)}`, { method: "PATCH", body }),
  remove: (name: string) => call<void>(`/agents/${enc(name)}`, { method: "DELETE" }),
  // Read-only discovery: installed-but-unregistered agents the user can add.
  candidates: () => call<AgentCandidatesOut>("/agents/candidates"),

  // Config files are read AND written in-app. A write carries the fingerprint
  // from the read that seeded the editor, so a file changed underneath the
  // editor is refused (409) rather than overwritten.
  listConfigFiles: (name: string) => call<ConfigFileListOut>(`/agents/${enc(name)}/config-files`),
  readConfigFile: (name: string, key: string) =>
    call<ConfigFileContent>(`/agents/${enc(name)}/config-files/${enc(key)}`),
  writeConfigFile: (name: string, key: string, body: ConfigFileWrite) =>
    call<ConfigFileInfo>(`/agents/${enc(name)}/config-files/${enc(key)}`, {
      method: "PUT",
      body,
    }),

  mcpStatus: (name: string) => call<McpInstallStatus>(`/agents/${enc(name)}/mcp-install`),
  mcpInstall: (name: string) =>
    call<McpInstallStatus>(`/agents/${enc(name)}/mcp-install`, { method: "POST" }),
  mcpUninstall: (name: string) =>
    call<McpInstallStatus>(`/agents/${enc(name)}/mcp-install`, { method: "DELETE" }),

  // MCP entries (specs agent-registry/005 workspace amendment)
  mcpEntries: (name: string) => call<McpEntriesResponse>(`/agents/${enc(name)}/mcp-entries`),
  // Deletes the entry from the agent's own config file (a .bak is written by
  // the daemon). `source` names which config file the entry came from — an
  // entry name can repeat across sources.
  removeMcpEntry: (name: string, entry: string, source?: string) => {
    const qs = source ? `?source=${enc(source)}` : "";
    return call<void>(`/agents/${enc(name)}/mcp-entries/${enc(entry)}${qs}`, {
      method: "DELETE",
    });
  },
  adoptMcpEntry: (name: string, entry: string, body: AdoptMcpEntryBody) =>
    call<{ kind: string; name: string }>(`/agents/${enc(name)}/mcp-entries/${enc(entry)}/adopt`, {
      method: "POST",
      body,
    }),

  // Plugins (spec agent-registry, workspace amendment). Enable/disable
  // writes the agent's documented config surface; uninstall drops the entry
  // (Codex) or delegates to the agent's own CLI (Claude Code).
  plugins: (name: string) => call<PluginsResponse>(`/agents/${enc(name)}/plugins`),
  togglePlugin: (name: string, id: string, enabled: boolean) =>
    call<void>(`/agents/${enc(name)}/plugins/${enc(id)}`, { method: "PATCH", body: { enabled } }),
  uninstallPlugin: (name: string, id: string) =>
    call<void>(`/agents/${enc(name)}/plugins/${enc(id)}`, { method: "DELETE" }),

  // Config-file child (per-file inside a directory-backed config key).
  readConfigChild: (name: string, key: string, relpath: string) =>
    call<ConfigFileContent>(
      `/agents/${enc(name)}/config-files/${enc(key)}/files/${childPath(relpath)}`,
    ),
  writeConfigChild: (name: string, key: string, relpath: string, body: ConfigFileWrite) =>
    call<ConfigFileInfo>(
      `/agents/${enc(name)}/config-files/${enc(key)}/files/${childPath(relpath)}`,
      { method: "PUT", body },
    ),

  // Unmanaged skills (specs agent-registry/005 workspace amendment)
  unmanagedSkills: (name: string) =>
    call<UnmanagedSkillsResponse>(`/agents/${enc(name)}/unmanaged-skills`),
  adoptUnmanagedSkill: (name: string, skill: string, location: string) =>
    call<{ name: string }>(`/agents/${enc(name)}/unmanaged-skills/${enc(skill)}/adopt`, {
      method: "POST",
      body: { location },
    }),
  deleteUnmanagedSkill: (name: string, skill: string, location: string) =>
    call<void>(`/agents/${enc(name)}/unmanaged-skills/${enc(skill)}?location=${enc(location)}`, {
      method: "DELETE",
    }),
};
