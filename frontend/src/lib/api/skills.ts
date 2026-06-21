// frontend/src/lib/api/skills.ts — typed fetch helpers for /api/v1/skills/*

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export type SkillSourceType = "local_import";

export interface LocalImportSource {
  type: "local_import";
  original_path: string;
}

export type SkillSource = LocalImportSource;

export type LinkMode = "symlink" | "junction" | "copy_fallback";

export interface SkillBindingOut {
  agent_name: string;
  enabled: boolean;
  last_linked_at: string | null;
  last_link_path: string | null;
  link_mode: LinkMode | null;
}

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
}

export interface SkillListOut {
  items: SkillOut[];
}

export interface SkillImportRequest {
  path: string;
  overwrite?: boolean;
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

export interface RepairReportOut {
  remediated: DriftEntryOut[];
  remaining: DriftReportOut;
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
  get: (name: string) => call<SkillOut>("GET", `/skills/${enc(name)}`),
  remove: (name: string) => call<void>("DELETE", `/skills/${enc(name)}`),
  enable: (name: string, body: SkillEnableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${enc(name)}/enable`, body),
  disable: (name: string, body: SkillDisableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${enc(name)}/disable`, body),
  verify: () => call<DriftReportOut>("POST", "/skills/verify"),
  repair: () => call<RepairReportOut>("POST", "/skills/repair"),
  filesTree: (name: string) => call<SkillFileTreeOut>("GET", `/skills/${enc(name)}/files`),
  fileContent: (name: string, path: string) =>
    call<SkillFileContentOut>("GET", `/skills/${enc(name)}/files/content?path=${enc(path)}`),
};
