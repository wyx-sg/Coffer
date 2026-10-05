// frontend/src/lib/api/skills.ts — request helpers for /api/v1/skills/*
//
// Every route here takes the skill's `uid`. The name is still the master
// folder's name on disk and the label every surface prints, but it is a label:
// the uid is the only thing a request may be built from
// (ADR identity-is-the-uid-inside-the-file).
//
// Wire types are aliases of the skill-manager contract's generated schemas
// (`generated/skill-manager.ts`). Transport via the typed client
// (.agents/frontend.md §4).
//
// Sources (spec skill-manager "Add skills from an archive", "Add skills from a
// Git repository"): a folder, an archive or a repository is STAGED first — the
// daemon answers what it found and writes nothing — then CONFIRMED with the
// chosen names (and the taken ones to replace), or CANCELLED, which removes
// the stage. A change of a Git-imported skill's source is a stage too, so the
// same cancel closes it. A skill's update is not applied by Coffer: its
// hand-off goes to the person's agent (spec skill-manager "Hand a Git-imported
// skill's update to an agent").

import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components as SkillManagerWire } from "@/lib/api/generated/skill-manager";

type Schemas = SkillManagerWire["schemas"];

export type SkillOut = Schemas["SkillOut"];
export type SkillFileNode = Schemas["SkillFileNodeOut"];

export type SkillFileContentOut = Schemas["SkillFileContentOut"];

export type SkillSourceStatus = Schemas["SkillSourceStatusOut"];
export type GitImportSource = Schemas["GitImportSourceOut"];
export type SkillStaging = Schemas["SkillStagingOut"];
export type StagedSkill = Schemas["StagedSkillOut"];
export type SkillStagingConfirm = Schemas["SkillStagingConfirmRequest"];
export type SkillStageGit = Schemas["SkillStageGitRequest"];
export type SkillSourceChange = Schemas["SkillSourceChangeOut"];
export type SkillSourceChangeFile = Schemas["SkillSourceChangeFileOut"];
export type SkillFileChange = Schemas["SkillFileChangeOut"];
export type SkillUpdateCheckInterval = Schemas["SkillUpdateCheckSettingBody"]["interval"];
export type SkillDriftEntry = Schemas["DriftEntryOut"];
export type SkillBulkDeleteResult = Schemas["SkillBulkDeleteResult"];
export type SkillRepairReport = Schemas["RepairReportOut"];

const skillPath = (uid: string) => ({ uid });

export const skillsApi = {
  list: () => unwrap(getApiClient().GET("/skills")),
  /** Delete one skill. Without `keepForeignCopies` an agent's folder that is no
   *  longer Coffer's link refuses the delete (409 SKILL_COPY_NOT_OURS); with it
   *  the skill goes and that folder is left alone (reported in `kept_copies`). */
  remove: (uid: string, keepForeignCopies = false) =>
    unwrap(
      getApiClient().DELETE("/skills/{uid}", {
        params: {
          path: skillPath(uid),
          ...(keepForeignCopies ? { query: { keep_foreign_copies: true } } : {}),
        },
      }),
    ),
  /** Delete several skills in one call: one result per skill, a refused one
   *  never stops the others. */
  bulkDelete: (uids: string[], keepForeignCopies = false) =>
    unwrap(
      getApiClient().POST("/skills/bulk-delete", {
        body: { uids, keep_foreign_copies: keepForeignCopies },
      }),
    ),
  filesTree: (uid: string) =>
    unwrap(getApiClient().GET("/skills/{uid}/files", { params: { path: skillPath(uid) } })),
  fileContent: (uid: string, path: string) =>
    unwrap(
      getApiClient().GET("/skills/{uid}/files/content", {
        params: { path: skillPath(uid), query: { path } },
      }),
    ),

  // ----- sources: stage → confirm | cancel -----
  stageFolder: (path: string) =>
    unwrap(getApiClient().POST("/skills/stage/folder", { body: { path } })),
  stageArchive: (file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    // A FormData body goes out as it is, with no Content-Type: the browser
    // sets the multipart boundary itself.
    return unwrap(
      getApiClient().POST("/skills/stage/archive", {
        body: { file: "" },
        bodySerializer: () => form,
      }),
    );
  },
  stageGit: (body: SkillStageGit) => unwrap(getApiClient().POST("/skills/stage/git", { body })),
  confirmStage: (stagingId: string, body: SkillStagingConfirm) =>
    unwrap(
      getApiClient().POST("/skills/stage/{staging_id}/confirm", {
        params: { path: { staging_id: stagingId } },
        body,
      }),
    ),
  cancelStage: (stagingId: string) =>
    unwrapVoid(
      getApiClient().DELETE("/skills/stage/{staging_id}", {
        params: { path: { staging_id: stagingId } },
      }),
    ),

  // ----- a Git-imported skill's updates -----
  checkSource: (uid: string) =>
    unwrap(getApiClient().POST("/skills/{uid}/source/check", { params: { path: skillPath(uid) } })),
  /** The prompt that hands the skill's update to an agent; refused 409 when none is waiting. */
  updateHandoff: (uid: string) =>
    unwrap(
      getApiClient().POST("/skills/{uid}/source/handoff", { params: { path: skillPath(uid) } }),
    ),
  /** "I merged it": pin the skill to the commit the agent merged. */
  recordMerged: (uid: string, commit: string) =>
    unwrap(
      getApiClient().POST("/skills/{uid}/source/merged", {
        params: { path: skillPath(uid) },
        body: { commit },
      }),
    ),
  /** How often this machine checks skills for updates in the background. */
  updateCheck: () => unwrap(getApiClient().GET("/skills/update-check")),
  setUpdateCheck: (interval: SkillUpdateCheckInterval) =>
    unwrap(getApiClient().PUT("/skills/update-check", { body: { interval } })),

  changeSource: (uid: string, body: SkillStageGit) =>
    unwrap(
      getApiClient().POST("/skills/{uid}/source/change", {
        params: { path: skillPath(uid) },
        body,
      }),
    ),
  applySourceChange: (uid: string, stagingId: string) =>
    unwrap(
      getApiClient().POST("/skills/{uid}/source/change/apply", {
        params: { path: skillPath(uid) },
        body: { staging_id: stagingId },
      }),
    ),

  // ----- agents' copies (spec skill-manager "Report skill drift on request") -----
  verify: () => unwrap(getApiClient().POST("/skills/verify")),
  repair: () => unwrap(getApiClient().POST("/skills/repair")),
  /** One agent's folder in the way of the skill's link, against master. */
  compareCopy: (uid: string, agentUid: string) =>
    unwrap(
      getApiClient().GET("/skills/{uid}/copies/{agent_uid}", {
        params: { path: { uid, agent_uid: agentUid } },
      }),
    ),
  /** Keep master (the folder is backed up and linked) or the agent's version. */
  resolveCopy: (uid: string, agentUid: string, keep: "master" | "agent") =>
    unwrap(
      getApiClient().POST("/skills/{uid}/copies/{agent_uid}/resolve", {
        params: { path: { uid, agent_uid: agentUid } },
        body: { keep },
      }),
    ),

  // ----- folders in the store no skill claims -----
  orphans: () => unwrap(getApiClient().GET("/skills/orphans")),
  orphanFiles: (name: string) =>
    unwrap(getApiClient().GET("/skills/orphans/{name}/files", { params: { path: { name } } })),
  orphanFileContent: (name: string, path: string) =>
    unwrap(
      getApiClient().GET("/skills/orphans/{name}/files/content", {
        params: { path: { name }, query: { path } },
      }),
    ),
  adoptOrphan: (name: string) =>
    unwrap(getApiClient().POST("/skills/orphans/{name}/adopt", { params: { path: { name } } })),
  removeOrphan: (name: string) =>
    unwrapVoid(getApiClient().DELETE("/skills/orphans/{name}", { params: { path: { name } } })),
};
