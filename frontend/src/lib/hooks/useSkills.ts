// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  catalogApi,
  skillsApi,
  type SkillDisableRequest,
  type SkillEnableRequest,
  type SkillFetchRequest,
  type SkillImportRequest,
  type SkillUpdateRequest,
} from "@/lib/api/skills";
import { useToast } from "@/components/ui/toast";

const SKILLS_KEY = ["skills"] as const;

/** Shared onError → toast handler for the single-use skill mutations. */
function useSkillToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useSkills() {
  return useQuery({
    queryKey: SKILLS_KEY,
    queryFn: async () => (await skillsApi.list()).items,
  });
}

export function useSkill(name: string) {
  return useQuery({
    queryKey: ["skills", name],
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
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

export function useFetchSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (body: SkillFetchRequest) => skillsApi.fetchGit(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

export function useCatalog(query: string) {
  return useQuery({
    queryKey: ["skill-catalog", query],
    queryFn: async () => (await catalogApi.list(query)).items,
  });
}

export function useInstallCatalogSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (name: string) => catalogApi.install(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

export function useEnableSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (vars: { name: string; body: SkillEnableRequest }) =>
      skillsApi.enable(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

export function useDisableSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (vars: { name: string; body: SkillDisableRequest }) =>
      skillsApi.disable(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
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
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

export function useUpdateSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (vars: { name: string; body?: SkillUpdateRequest }) =>
      skillsApi.update(vars.name, vars.body ?? {}),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
      qc.invalidateQueries({ queryKey: ["skills", vars.name] });
      qc.invalidateQueries({ queryKey: ["skills", vars.name, "files"] });
    },
    onError,
  });
}

export function useVerifySkills() {
  return useMutation({
    mutationFn: () => skillsApi.verify(),
  });
}

export function useSkillFiles(name: string) {
  return useQuery({
    queryKey: ["skills", name, "files"],
    queryFn: async () => (await skillsApi.filesTree(name)).root,
    enabled: !!name,
  });
}

export function useSkillFileContent(name: string, path: string | null) {
  return useQuery({
    queryKey: ["skills", name, "file", path ?? ""],
    queryFn: () => skillsApi.fileContent(name, path as string),
    enabled: !!name && !!path,
  });
}
