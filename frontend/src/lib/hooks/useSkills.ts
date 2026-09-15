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

export function useSkill(name: string) {
  return useQuery({
    queryKey: skillKey(name),
    queryFn: () => skillsApi.get(name),
    enabled: !!name,
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
    mutationFn: (name: string) => skillsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: skillsKey });
    },
    onError,
  });
}

export function useSkillFiles(name: string) {
  return useQuery({
    queryKey: skillFilesKey(name),
    queryFn: async () => (await skillsApi.filesTree(name)).root,
    enabled: !!name,
  });
}

export function useSkillFileContent(name: string, path: string | null) {
  return useQuery({
    queryKey: skillFileKey(name, path ?? ""),
    queryFn: () => skillsApi.fileContent(name, path as string),
    enabled: !!name && !!path,
  });
}
