// frontend/src/lib/api/skills.ts — request helpers for /api/v1/skills/*
//
// Every route here takes the skill's `uid`. The name is still the master
// folder's name on disk and the label every surface prints, but it is a label:
// renaming a skill moves the folder and leaves the uid alone, so the uid is the
// only thing a request may be built from (ADR resource-identity-is-an-immutable-uid).
//
// Wire types are aliases of the skill-manager contract's generated schemas
// (`generated/skill-manager.ts`). Transport via the shared `call`
// (.agents/frontend.md §4).

import { call, enc } from "@/lib/api/call";
import type { components as SkillManagerWire } from "@/lib/api/generated/skill-manager";

export type SkillOut = SkillManagerWire["schemas"]["SkillOut"];

export type SkillListOut = SkillManagerWire["schemas"]["SkillListOut"];

export type SkillImportRequest = SkillManagerWire["schemas"]["SkillImportRequest"];

export type SkillFileNode = SkillManagerWire["schemas"]["SkillFileNodeOut"];

export type SkillFileTreeOut = SkillManagerWire["schemas"]["SkillFileTreeOut"];

/** Body of a skill-file save. `expected_fingerprint` makes the write
 *  conditional: the daemon refuses it with 409 SKILL_FILE_STALE when the file
 *  changed on disk since the read that produced the fingerprint. The master
 *  folder is also the user's own working copy, so that race is routine. */
export type SkillFileWrite = SkillManagerWire["schemas"]["SkillFileWriteRequest"];

export type SkillFileContentOut = SkillManagerWire["schemas"]["SkillFileContentOut"];

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
