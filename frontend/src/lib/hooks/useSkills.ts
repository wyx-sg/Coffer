// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { skillCompareKey, skillFileKey, skillFilesKey, skillsKey } from "@/lib/api/queryKeys";
import { skillsApi, type SkillImportRequest } from "@/lib/api/skills";
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

export function useImportSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (body: SkillImportRequest) => skillsApi.importLocal(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: skillsKey });
    },
    onError,
  });
}

export function useRemoveSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (uid: string) => skillsApi.remove(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: skillsKey });
    },
    onError,
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

// ----- a Git-imported skill's updates (spec skill-manager "Update a
// Git-imported skill from its source") -----

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

/** Stage an update preview. No toast: the dialog shows why it cannot preview. */
export function usePreviewSkillUpdate() {
  return useMutation({
    mutationFn: (uid: string) => skillsApi.previewUpdate(uid),
  });
}

/** Apply a previewed update. No toast: a conflict (409) is rendered by the
 *  dialog, which then offers Take theirs. */
export function useApplySkillUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; stagingId: string; discardLocalEdits: boolean }) =>
      skillsApi.applyUpdate(vars.uid, {
        staging_id: vars.stagingId,
        discard_local_edits: vars.discardLocalEdits,
      }),
    onSuccess: (_d, vars) => {
      void qc.invalidateQueries({ queryKey: skillsKey });
      void qc.invalidateQueries({ queryKey: skillFilesKey(vars.uid) });
    },
  });
}

export function useKeepSkillEdits() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (vars: { uid: string; commit: string | null }) =>
      skillsApi.keepMine(vars.uid, vars.commit),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
    onError,
  });
}

/** One file's local / pinned / incoming text in a staged update. */
export function useSkillUpdateCompare(uid: string, stagingId: string | null, path: string | null) {
  return useQuery({
    queryKey: skillCompareKey(uid, stagingId ?? "", path ?? ""),
    queryFn: () => skillsApi.compareUpdate(uid, stagingId as string, path as string),
    enabled: !!uid && !!stagingId && !!path,
  });
}

// ----- agents' copies (spec skill-manager "Report skill drift on request") -----

/** Run the read-only drift report (Check copies). A mutation, not a query:
 *  it is asked for, never polled. */
export function useCheckSkillCopies() {
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: () => skillsApi.verify(),
    onError,
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
