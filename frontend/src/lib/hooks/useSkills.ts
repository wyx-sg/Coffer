// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  skillsApi,
  type SkillDisableRequest,
  type SkillEnableRequest,
  type SkillFetchRequest,
  type SkillImportRequest,
} from "@/lib/api/skills";

const SKILLS_KEY = ["skills"] as const;

export function useSkills() {
  return useQuery({
    queryKey: SKILLS_KEY,
    queryFn: async () => (await skillsApi.list()).items,
  });
}

export function useImportSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SkillImportRequest) => skillsApi.importLocal(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
  });
}

export function useFetchSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SkillFetchRequest) => skillsApi.fetchGit(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
  });
}

export function useEnableSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: SkillEnableRequest }) =>
      skillsApi.enable(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
  });
}

export function useDisableSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; body: SkillDisableRequest }) =>
      skillsApi.disable(vars.name, vars.body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
  });
}

export function useRemoveSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => skillsApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
  });
}

export function useVerifySkills() {
  return useMutation({
    mutationFn: () => skillsApi.verify(),
  });
}
