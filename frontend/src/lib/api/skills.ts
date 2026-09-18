// frontend/src/lib/api/skills.ts — request helpers for /api/v1/skills/*
//
// Every route here takes the skill's `uid`. The name is still the master
// folder's name on disk and the label every surface prints, but it is a label:
// renaming a skill moves the folder and leaves the uid alone, so the uid is the
// only thing a request may be built from (ADR resource-identity-is-an-immutable-uid).
//
// Wire types are hand-written here; the skill-manager contract also generates
// into `generated/skill-manager.ts` (`npm run codegen`, `scripts/codegen.mjs`).
// Transport via the shared `call` (.agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { Scope } from "@/lib/hooks/useScope";

interface LocalImportSource {
  type: "local_import";
  original_path: string;
}

type SkillSource = LocalImportSource;

type LinkMode = "symlink" | "junction" | "copy_fallback";

/** One agent currently holding a delivered copy of this skill. Delivery
 *  bookkeeping surfaced read-only: a row here simply means "delivered". Who
 *  gets a row is decided by `SkillOut.enabled` + `SkillOut.scope`. */
interface SkillBindingOut {
  /** The agent holding the copy, as the identity a stored pointer has to be.
   *  Address this. */
  agent_uid: string;
  /** The same agent's label, resolved at read time. Display this — a line of
   *  UUIDs under a skill tells the reader nothing. */
  agent_name: string;
  last_linked_at: string | null;
  last_link_path: string | null;
  link_mode: LinkMode | null;
}

export interface SkillOut {
  /** The skill Resource's immutable identity — what every route below takes. */
  uid: string;
  /** A mutable label, and also the master folder's name on disk. For display. */
  name: string;
  description: string;
  source: SkillSource;
  /** The two halves of the delivery predicate: a skill reaches an agent iff
   *  `enabled` and that agent, on this machine, falls inside `scope`
   *  (null = everywhere; an axis given [] matches nothing). */
  enabled: boolean;
  scope: Scope | null;
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

/** Body of a skill-file save. `expected_fingerprint` makes the write
 *  conditional: the daemon refuses it with 409 SKILL_FILE_STALE when the file
 *  changed on disk since the read that produced the fingerprint. The master
 *  folder is also the user's own working copy, so that race is routine. */
export interface SkillFileWrite {
  path: string;
  content: string;
  expected_fingerprint?: string | null;
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
  /** sha256 of the file's RAW on-disk bytes — not of `content`, which is
   *  truncated past the read cap and empty for a binary file. Echo it back on a
   *  save to make that save conditional. */
  fingerprint: string;
}

export const skillsApi = {
  list: () => call<SkillListOut>("/skills"),
  importLocal: (body: SkillImportRequest) =>
    call<SkillOut>("/skills/import", { method: "POST", body }),
  get: (uid: string) => call<SkillOut>(`/skills/${enc(uid)}`),
  remove: (uid: string) => call<void>(`/skills/${enc(uid)}`, { method: "DELETE" }),
  filesTree: (uid: string) => call<SkillFileTreeOut>(`/skills/${enc(uid)}/files`),
  fileContent: (uid: string, path: string) =>
    call<SkillFileContentOut>(`/skills/${enc(uid)}/files/content?path=${enc(path)}`),
  writeFileContent: (uid: string, body: SkillFileWrite) =>
    call<SkillFileContentOut>(`/skills/${enc(uid)}/files/content`, { method: "PUT", body }),
};
