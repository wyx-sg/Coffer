// frontend/src/lib/api/skills.ts — typed fetch helpers for /api/v1/skills/*

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export type SkillSourceType = "local_import" | "git";

export interface LocalImportSource {
  type: "local_import";
  original_path: string;
}

export interface GitSource {
  type: "git";
  git_url: string;
  git_ref: string;
  git_subpath: string;
}

export type SkillSource = LocalImportSource | GitSource;

export type LinkMode = "symlink" | "junction" | "copy_fallback";

export interface SkillBindingOut {
  agent_name: string;
  enabled: boolean;
  last_linked_at: string | null;
  last_link_path: string | null;
  link_mode: LinkMode | null;
}

export type ScanVerdict = "low" | "medium" | "high" | "critical";

export interface SkillOut {
  name: string;
  description: string;
  source: SkillSource;
  enabled: boolean;
  version_hash: string;
  master_path: string;
  last_synced_from_source_at: string | null;
  created_at: string;
  updated_at: string;
  bindings: SkillBindingOut[];
  // Trust layer L2 (FR-028/FR-029). Always sent by the backend; optional here
  // so existing fixtures/consumers predating the trust layer still type-check.
  scan_verdict?: ScanVerdict | null;
  scan_findings_count?: number;
  last_scanned_at?: string | null;
  risk_acknowledged?: boolean;
  requires_acknowledgment?: boolean;
}

export interface SkillListOut {
  items: SkillOut[];
}

export interface SkillImportRequest {
  path: string;
}

export interface SkillFetchRequest {
  git_url: string;
  git_ref: string;
  git_subpath?: string;
}

export interface SkillUpdateRequest {
  allow_rename?: boolean;
}

export interface SkillUpdateResult {
  skill: SkillOut;
  changed: boolean;
  renamed_from: string | null;
}

export interface SkillEnableRequest {
  agent_name: string;
  force?: boolean;
}

export interface SkillDisableRequest {
  agent_name: string;
}

export interface DriftEntryOut {
  skill_name: string;
  agent_name: string;
  kind: string;
  target_path: string;
  suggested_remedy: string;
}

export interface DriftReportOut {
  entries: DriftEntryOut[];
}

export interface SkillFileNode {
  name: string;
  path: string;
  /** Absolute on-disk path of this node (file viewers hand it to FileActions). */
  abs_path?: string;
  type: "file" | "dir";
  size: number | null;
  /** True on a dir whose children were clipped at the max tree depth. */
  truncated: boolean;
  children: SkillFileNode[] | null;
}

export interface SkillFileTreeOut {
  root: SkillFileNode;
}

export interface SkillFileContentOut {
  path: string;
  /** Absolute on-disk path of the file (handed to FileActions). */
  abs_path?: string;
  /** Absolute on-disk path of the file's containing folder. */
  folder_abs_path?: string;
  content: string;
  truncated: boolean;
  binary: boolean;
  size: number;
}

async function call<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
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

// Skill names and file paths are interpolated into URL paths / query params;
// encode them so a name/path with URL-significant characters can't malform or
// misroute the request (defence in depth — the daemon also constrains names
// server-side).
const enc = encodeURIComponent;

export const skillsApi = {
  list: () => call<SkillListOut>("GET", "/skills"),
  importLocal: (body: SkillImportRequest) => call<SkillOut>("POST", "/skills/import", body),
  fetchGit: (body: SkillFetchRequest) => call<SkillOut>("POST", "/skills/fetch", body),
  get: (name: string) => call<SkillOut>("GET", `/skills/${enc(name)}`),
  remove: (name: string) => call<void>("DELETE", `/skills/${enc(name)}`),
  update: (name: string, body: SkillUpdateRequest) =>
    call<SkillUpdateResult>("POST", `/skills/${enc(name)}/update`, body),
  enable: (name: string, body: SkillEnableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${enc(name)}/enable`, body),
  disable: (name: string, body: SkillDisableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${enc(name)}/disable`, body),
  verify: () => call<DriftReportOut>("POST", "/skills/verify"),
  filesTree: (name: string) => call<SkillFileTreeOut>("GET", `/skills/${enc(name)}/files`),
  fileContent: (name: string, path: string) =>
    call<SkillFileContentOut>("GET", `/skills/${enc(name)}/files/content?path=${enc(path)}`),
};
