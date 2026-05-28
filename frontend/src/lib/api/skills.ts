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

async function call<T>(
  method: "GET" | "POST" | "DELETE",
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

export const skillsApi = {
  list: () => call<SkillListOut>("GET", "/skills"),
  importLocal: (body: SkillImportRequest) => call<SkillOut>("POST", "/skills/import", body),
  fetchGit: (body: SkillFetchRequest) => call<SkillOut>("POST", "/skills/fetch", body),
  get: (name: string) => call<SkillOut>("GET", `/skills/${name}`),
  remove: (name: string) => call<void>("DELETE", `/skills/${name}`),
  update: (name: string, body: SkillUpdateRequest) =>
    call<SkillUpdateResult>("POST", `/skills/${name}/update`, body),
  enable: (name: string, body: SkillEnableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${name}/enable`, body),
  disable: (name: string, body: SkillDisableRequest) =>
    call<SkillBindingOut>("POST", `/skills/${name}/disable`, body),
  verify: () => call<DriftReportOut>("POST", "/skills/verify"),
};
