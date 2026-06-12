// frontend/src/lib/api/agents.ts — typed fetch helpers for /api/v1/agents/*
// Until openapi codegen merges specs 003/004, we hand-write the wire types
// to match `specs/004-agent-registry/contracts/api.openapi.yaml`.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export type AgentType = "claude_code" | "codex";

export type ConfigFileFormat = "json" | "toml" | "markdown" | "text";

export interface ConfigFileInfo {
  key: string;
  display_name: string;
  path: string;
  format: ConfigFileFormat;
  exists: boolean;
  size: number | null;
  modified_at: string | null;
}

export interface ConfigFileListOut {
  items: ConfigFileInfo[];
}

export interface ConfigFileContent {
  key: string;
  format: ConfigFileFormat;
  exists: boolean;
  content: string;
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

async function call<T>(
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
    );
  }
  return data as T;
}

// Agent names and config-file keys are interpolated into URL paths; encode them
// so a name/key with URL-significant characters can't malform or misroute the
// request (defence in depth — the daemon also constrains names server-side).
const enc = encodeURIComponent;

export const agentsApi = {
  list: () => call<AgentListOut>("GET", "/agents"),
  register: (body: AgentCreate) => call<AgentOut>("POST", "/agents", body),
  get: (name: string) => call<AgentOut>("GET", `/agents/${enc(name)}`),
  patch: (name: string, body: AgentPatch) => call<AgentOut>("PATCH", `/agents/${enc(name)}`, body),
  remove: (name: string) => call<void>("DELETE", `/agents/${enc(name)}`),
  // Read-only discovery: installed-but-unregistered agents the user can add.
  candidates: () => call<AgentCandidatesOut>("GET", "/agents/candidates"),

  listConfigFiles: (name: string) =>
    call<ConfigFileListOut>("GET", `/agents/${enc(name)}/config-files`),
  readConfigFile: (name: string, key: string) =>
    call<ConfigFileContent>("GET", `/agents/${enc(name)}/config-files/${enc(key)}`),
  // Atomic write (a `.bak` of the prior content is kept). Returns the refreshed
  // metadata view. Malformed JSON/TOML is rejected server-side (422) and the
  // on-disk file is left unchanged.
  writeConfigFile: (name: string, key: string, content: string) =>
    call<ConfigFileInfo>("PUT", `/agents/${enc(name)}/config-files/${enc(key)}`, { content }),

  mcpStatus: (name: string) => call<McpInstallStatus>("GET", `/agents/${enc(name)}/mcp-install`),
  mcpInstall: (name: string) => call<McpInstallStatus>("POST", `/agents/${enc(name)}/mcp-install`),
  mcpUninstall: (name: string) =>
    call<McpInstallStatus>("DELETE", `/agents/${enc(name)}/mcp-install`),
};

export interface NativeMemoryProject {
  slug: string;
  memory_dir: string;
  fact_count: number;
  managed: boolean;
}

export interface NativeMemoryOut {
  projects: NativeMemoryProject[];
  unmanaged_fact_count: number;
}

export async function getAgentNativeMemory(name: string): Promise<NativeMemoryOut> {
  return call<NativeMemoryOut>("GET", `/agents/${enc(name)}/native-memory`);
}
