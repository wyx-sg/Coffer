// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  skillCopiesKey,
  skillFileKey,
  skillFilesKey,
  skillsKey,
  skillUpdateCheckKey,
} from "@/lib/api/queryKeys";
import { skillsApi, type SkillUpdateCheckInterval } from "@/lib/api/skills";
import { useToast } from "@/components/ui/toast";

/** Shared onError → toast handler for the single-use skill mutations. */
function useSkillToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useSkills() {
  return useQuery({
    queryKey: skillsKey,
    queryFn: async () => (await skillsApi.list()).items,
  });
}

/** Delete a skill. No toast here: the confirmation renders a refusal inline (an
 *  agent's copy that is no longer Coffer's link) and stays open on it, offering
 *  to delete and keep that folder (`keepForeignCopies`). */
export function useRemoveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; keepForeignCopies?: boolean }) =>
      vars.keepForeignCopies ? skillsApi.remove(vars.uid, true) : skillsApi.remove(vars.uid),
    onSuccess: (_d, vars) => {
      qc.removeQueries({ queryKey: [...skillsKey, vars.uid] });
      void qc.invalidateQueries({ queryKey: skillsKey });
    },
  });
}

/** Delete several skills behind one confirmation (POST /skills/bulk-delete).
 *  No toast: the dialog says how many went and which were refused, and offers
 *  to delete those and keep the agents' folders. */
export function useBulkDeleteSkills() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uids: string[]; keepForeignCopies?: boolean }) =>
      vars.keepForeignCopies
        ? skillsApi.bulkDelete(vars.uids, true)
        : skillsApi.bulkDelete(vars.uids),
    onSuccess: (out) => {
      for (const r of out.results) {
        if (r.deleted) qc.removeQueries({ queryKey: [...skillsKey, r.uid] });
      }
      void qc.invalidateQueries({ queryKey: skillsKey });
    },
  });
}

export function useSkillFiles(uid: string) {
  return useQuery({
    queryKey: skillFilesKey(uid),
    queryFn: async () => (await skillsApi.filesTree(uid)).root,
    enabled: !!uid,
  });
}

export function useSkillFileContent(uid: string, path: string | null) {
  return useQuery({
    queryKey: skillFileKey(uid, path ?? ""),
    queryFn: () => skillsApi.fileContent(uid, path as string),
    enabled: !!uid && !!path,
  });
}

// ----- sources: stage → confirm | cancel (spec skill-manager "Add skills from
// an archive", "Add skills from a Git repository") -----

/** What to stage: a folder path, an uploaded archive, or a repository. */
/** @ui-only mutation argument; never crosses the wire. */
export type SkillStageInput =
  | { kind: "folder"; path: string }
  | { kind: "archive"; file: File }
  | { kind: "git"; url: string; ref?: string | null; path?: string | null };

/** Stage a source. No toast: the dialog renders the refusal inline (an unsafe
 *  archive names its entries, git names what it could not reach). */
export function useStageSkillSource() {
  return useMutation({
    mutationFn: (input: SkillStageInput) => {
      if (input.kind === "folder") return skillsApi.stageFolder(input.path);
      if (input.kind === "archive") return skillsApi.stageArchive(input.file);
      return skillsApi.stageGit({
        url: input.url,
        ref: input.ref ?? null,
        path: input.path ?? null,
      });
    },
  });
}

/** Confirm a stage. No toast: a taken name comes back as 409 and the dialog
 *  offers Replace on that row instead. */
export function useConfirmSkillStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { stagingId: string; skills: string[]; replace: string[] }) =>
      skillsApi.confirmStage(vars.stagingId, { skills: vars.skills, replace: vars.replace }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
  });
}

/** Remove a stage (dialog closed, preview dismissed). Fire-and-forget: the
 *  daemon also sweeps a stage after an hour, so a failure here loses nothing. */
export function useCancelSkillStage() {
  return useMutation({
    mutationFn: (stagingId: string) => skillsApi.cancelStage(stagingId),
  });
}

// ----- a Git-imported skill's updates (spec skill-manager "Hand a
// Git-imported skill's update to an agent") -----

export function useCheckSkillSource() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (uid: string) => skillsApi.checkSource(uid),
    // The status rides on SkillOut, so the list and the detail both refetch.
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
    onError,
  });
}

/** The update's hand-off prompt, asked for when the person picks a verb of
 *  `AgentHandoff`. Writes nothing; a refusal reaches `AgentHandoff`'s toast. */
export function useSkillUpdateHandoff(uid: string) {
  return async (): Promise<string> => (await skillsApi.updateHandoff(uid)).handoff.prompt;
}

/** "I merged it": pin the skill to the commit its agent merged. No toast on
 *  success: the update stops being offered, which is the answer. */
export function useRecordSkillMerged() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; commit: string }) =>
      skillsApi.recordMerged(vars.uid, vars.commit),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
  });
}

/** Take a staged change of source. No toast: the dialog renders a refusal. */
export function useApplySkillSourceChange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; stagingId: string }) =>
      skillsApi.applySourceChange(vars.uid, vars.stagingId),
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: skillsKey });
      void qc.invalidateQueries({ queryKey: skillFilesKey(vars.uid) });
    },
  });
}

/** How often this machine checks skills for updates in the background
 *  (Settings › General); kept by the daemon, in effect at once. */
export function useSkillUpdateCheck() {
  return useQuery({
    queryKey: skillUpdateCheckKey,
    queryFn: () => skillsApi.updateCheck(),
    staleTime: 60_000,
  });
}

export function useSetSkillUpdateCheck() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (interval: SkillUpdateCheckInterval) => skillsApi.setUpdateCheck(interval),
    onSuccess: (out) => qc.setQueryData(skillUpdateCheckKey, out),
    onError,
  });
}

// ----- agents' copies (spec skill-manager "Report skill drift on request") -----

/** The read-only drift report (Check copies): read only when the person asks
 *  (Check copies / Check again call `refetch`), never when a page opens and
 *  never polled. A row names a folder in the way once a check has found it. */
export function useSkillCopies() {
  return useQuery({
    queryKey: skillCopiesKey,
    queryFn: () => skillsApi.verify(),
    // Reading every agent's skill folders is real work: it runs only when the
    // person asks (Check copies / Check again call `refetch`), never on opening
    // a page. What a check found stays cached for the session.
    enabled: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** Repair what the drift report says is safely repairable. */
export function useRepairSkillCopies() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: () => skillsApi.repair(),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
    onError,
  });
}
