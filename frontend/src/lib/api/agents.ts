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
  /** Absolute path of the containing folder. */
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

/** Session-start hook (rules-injection) install status — mirrors McpInstallStatus.
 * `command` is the resolved shim command line when installed, null otherwise. */
export interface HookInstallStatus {
  installed: boolean;
  command: string | null;
}

/** One of the agent's OWN native per-project memory stores (read-only scan). */
export interface NativeMemoryStore {
  /** Best-effort readable project label (the project dir's basename). */
  project: string;
  /** Best-effort decoded absolute project path, or null when undecodable. */
  path: string | null;
  /** Absolute path to the agent's native memory directory (the real identity). */
  memory_dir: string;
  /** Number of memory items (.md files, excluding the MEMORY.md index). */
  item_count: number;
}

export interface NativeMemoryListResponse {
  items: NativeMemoryStore[];
}

/** Result of importing one native memory store into Coffer (bulk remember →
 * inbox → organize). `store` is null when the project couldn't be resolved
 * (e.g. a lossy slug with no transcript, or a non-git project). */
export interface NativeMemoryImportResult {
  imported: number;
  skipped: number;
  store: string | null;
  project_path: string | null;
  organized: boolean;
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
  /** When true, the agent's own native memory is disabled (via its config) so it
   * uses Coffer as the shared memory store. Hand-added until openapi codegen. */
  disable_native_memory?: boolean;
  /** Per-agent model binding (spec 011 amendment 2026-06-22b). The model the
   * agent projects — null = unbound (falls back to the active connection). */
  model?: string | null;
  fast_model?: string | null;
  wire_api?: string | null;
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
  disable_native_memory?: boolean;
  // Per-agent model binding (E3); explicit null fast_model clears the fast slot.
  model?: string | null;
  fast_model?: string | null;
  wire_api?: string | null;
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

// Agent workspace wire types (MCP entries / plugins / unmanaged skills) live in
// agents-workspace.ts for the file-size budget; re-exported so existing
// `from "@/lib/api/agents"` import paths keep working.
export type {
  AdoptMcpEntryBody,
  MarketplaceOut,
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

  // Session-start hook (rules injection): install/uninstall/status. A 422 with
  // code HOOK_INSTALL_UNSUPPORTED means the agent type has no hook support.
  hookStatus: (name: string) =>
    call<HookInstallStatus>("GET", `/agents/${enc(name)}/hook-install`),
  hookInstall: (name: string) =>
    call<HookInstallStatus>("POST", `/agents/${enc(name)}/hook-install`),
  hookUninstall: (name: string) =>
    call<HookInstallStatus>("DELETE", `/agents/${enc(name)}/hook-install`),

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

  // Native memory: the agent's OWN per-project memory stores (read-only scan).
  nativeMemory: (name: string) =>
    call<NativeMemoryListResponse>("GET", `/agents/${enc(name)}/native-memory`),
  importNativeMemory: (name: string, memoryDir: string) =>
    call<NativeMemoryImportResult>("POST", `/agents/${enc(name)}/native-memory/import`, {
      memory_dir: memoryDir,
    }),
};
