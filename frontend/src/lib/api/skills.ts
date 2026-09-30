// frontend/src/lib/api/skills.ts — request helpers for /api/v1/skills/*
//
// Every route here takes the skill's `uid`. The name is still the master
// folder's name on disk and the label every surface prints, but it is a label:
// the uid is the only thing a request may be built from
// (ADR resource-identity-is-an-immutable-uid).
//
// Wire types are aliases of the skill-manager contract's generated schemas
// (`generated/skill-manager.ts`). Transport via the shared `call`
// (.agents/frontend.md §4).
//
// Sources (spec skill-manager "Add skills from an archive", "Add skills from a
// Git repository"): a folder, an archive or a repository is STAGED first — the
// daemon answers what it found and writes nothing — then CONFIRMED with the
// chosen names (and the taken ones to replace), or CANCELLED, which removes
// the stage. An update preview of a Git-imported skill is a stage too, so the
// same cancel closes it.

import { call, enc } from "@/lib/api/call";
import type { components as SkillManagerWire } from "@/lib/api/generated/skill-manager";

type Schemas = SkillManagerWire["schemas"];

export type SkillOut = Schemas["SkillOut"];
export type SkillListOut = Schemas["SkillListOut"];
export type SkillImportRequest = Schemas["SkillImportRequest"];
export type SkillFileNode = Schemas["SkillFileNodeOut"];
export type SkillFileTreeOut = Schemas["SkillFileTreeOut"];

/** Body of a skill-file save. `expected_fingerprint` makes the write
 *  conditional: the daemon refuses it with 409 SKILL_FILE_STALE when the file
 *  changed on disk since the read that produced the fingerprint. The master
 *  folder is also the user's own working copy, so that race is routine. */
export type SkillFileWrite = Schemas["SkillFileWriteRequest"];
export type SkillFileContentOut = Schemas["SkillFileContentOut"];

export type SkillSourceStatus = Schemas["SkillSourceStatusOut"];
export type GitImportSource = Schemas["GitImportSourceOut"];
export type SkillStaging = Schemas["SkillStagingOut"];
export type StagedSkill = Schemas["StagedSkillOut"];
export type SkillStagingConfirm = Schemas["SkillStagingConfirmRequest"];
export type SkillStagingConfirmOut = Schemas["SkillStagingConfirmOut"];
export type SkillStageGit = Schemas["SkillStageGitRequest"];
export type SkillUpdatePreview = Schemas["SkillUpdatePreviewOut"];
export type SkillFileChange = Schemas["SkillFileChangeOut"];
export type SkillUpdateCompare = Schemas["SkillUpdateCompareOut"];
export type SkillUpdateApply = Schemas["SkillUpdateApplyRequest"];
export type SkillDriftReport = Schemas["DriftReportOut"];
export type SkillDriftEntry = Schemas["DriftEntryOut"];
export type SkillRepairReport = Schemas["RepairReportOut"];
export type SkillCopyCompare = Schemas["SkillCopyCompareOut"];
export type SkillOrphanList = Schemas["SkillOrphanListOut"];

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

  // ----- sources: stage → confirm | cancel -----
  stageFolder: (path: string) =>
    call<SkillStaging>("/skills/stage/folder", { method: "POST", body: { path } }),
  stageArchive: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return call<SkillStaging>("/skills/stage/archive", { method: "POST", body: form });
  },
  stageGit: (body: SkillStageGit) =>
    call<SkillStaging>("/skills/stage/git", { method: "POST", body }),
  confirmStage: (stagingId: string, body: SkillStagingConfirm) =>
    call<SkillStagingConfirmOut>(`/skills/stage/${enc(stagingId)}/confirm`, {
      method: "POST",
      body,
    }),
  cancelStage: (stagingId: string) =>
    call<void>(`/skills/stage/${enc(stagingId)}`, { method: "DELETE" }),

  // ----- a Git-imported skill's updates -----
  checkSource: (uid: string) =>
    call<SkillSourceStatus>(`/skills/${enc(uid)}/source/check`, { method: "POST" }),
  previewUpdate: (uid: string) =>
    call<SkillUpdatePreview>(`/skills/${enc(uid)}/source/preview`, { method: "POST" }),
  compareUpdate: (uid: string, stagingId: string, path: string) =>
    call<SkillUpdateCompare>(
      `/skills/${enc(uid)}/source/compare?staging_id=${enc(stagingId)}&path=${enc(path)}`,
    ),
  applyUpdate: (uid: string, body: SkillUpdateApply) =>
    call<SkillOut>(`/skills/${enc(uid)}/source/apply`, { method: "POST", body }),
  keepMine: (uid: string, commit: string | null) =>
    call<SkillSourceStatus>(`/skills/${enc(uid)}/source/keep`, {
      method: "POST",
      body: { commit },
    }),

  changeSource: (uid: string, body: SkillStageGit) =>
    call<SkillUpdatePreview>(`/skills/${enc(uid)}/source/change`, { method: "POST", body }),

  // ----- agents' copies (spec skill-manager "Report skill drift on request") -----
  verify: () => call<SkillDriftReport>("/skills/verify", { method: "POST" }),
  repair: () => call<SkillRepairReport>("/skills/repair", { method: "POST" }),
  /** One agent's folder in the way of the skill's link, against master. */
  compareCopy: (uid: string, agentUid: string) =>
    call<SkillCopyCompare>(`/skills/${enc(uid)}/copies/${enc(agentUid)}`),
  /** Keep master (the folder is backed up and linked) or the agent's version. */
  resolveCopy: (uid: string, agentUid: string, keep: "master" | "agent") =>
    call<SkillOut>(`/skills/${enc(uid)}/copies/${enc(agentUid)}/resolve`, {
      method: "POST",
      body: { keep },
    }),

  // ----- folders in the store no skill claims -----
  orphans: () => call<SkillOrphanList>("/skills/orphans"),
  adoptOrphan: (name: string) =>
    call<SkillOut>(`/skills/orphans/${enc(name)}/adopt`, { method: "POST" }),
  removeOrphan: (name: string) => call<void>(`/skills/orphans/${enc(name)}`, { method: "DELETE" }),
};
