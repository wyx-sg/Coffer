// frontend/src/lib/hooks/useSkills.ts — TanStack Query bindings for skills.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { resourcesApi } from "@/lib/api/resources";
import { skillsApi, type RepairReportOut, type SkillImportRequest } from "@/lib/api/skills";
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

/** One half of useSetSkillEnabled: the kind-agnostic resource enable/disable
 *  call, but invalidating ["skills"] (which prefix-matches the single-skill
 *  ["skills", name] key too) instead of useResourceMutations' ["resources"] —
 *  the skills surfaces read the skills queries, not the resource list. */
function useSkillResourceToggle(mutate: (kind: string, name: string) => Promise<void>) {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation({
    mutationFn: (vars: { kind: string; name: string }) => mutate(vars.kind, vars.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
  });
}

/** The skill's own enable flag, as the skills list table's status switch drives
 *  it. One half of the delivery predicate (the other is the skill's scope);
 *  there is no per-agent binding toggle any more. */
export function useSetSkillEnabled() {
  return {
    enable: useSkillResourceToggle(resourcesApi.enable),
    disable: useSkillResourceToggle(resourcesApi.disable),
  };
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

export function useVerifySkills() {
  return useMutation({
    mutationFn: () => skillsApi.verify(),
  });
}

export function useRepairSkillDrift() {
  const qc = useQueryClient();
  const onError = useSkillToastError();
  return useMutation<RepairReportOut, unknown, void>({
    mutationFn: () => skillsApi.repair(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SKILLS_KEY });
    },
    onError,
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
