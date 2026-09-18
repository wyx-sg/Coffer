// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { skillFileKey, skillFilesKey, skillKey, skillsKey } from "@/lib/api/queryKeys";
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

export function useSkill(uid: string) {
  return useQuery({
    queryKey: skillKey(uid),
    queryFn: () => skillsApi.get(uid),
    enabled: !!uid,
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
