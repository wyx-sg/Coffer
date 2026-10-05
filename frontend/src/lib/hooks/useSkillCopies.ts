// frontend/src/lib/hooks/useSkillCopies.ts — TanStack Query bindings for an
// agent's copy in the way of a skill's link, the store's orphan folders and a
// Git skill's change of source (spec skill-manager "Resolve a folder in the
// way of a skill's link", "Act on a folder in the skills store that no skill
// claims", "Change a Git-imported skill's source").
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ReachMode } from "@/lib/reach/reachState";
import {
  resourcesKey,
  scopeKey,
  skillCopyKey,
  skillOrphanFileKey,
  skillOrphanFilesKey,
  skillOrphansKey,
  skillsKey,
} from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { scopeApi, type Scope } from "@/lib/api/scope";
import { skillsApi } from "@/lib/api/skills";

/** One agent's folder in the way, compared with master. Read while the
 *  compare dialog is open; a refusal renders in the dialog. */
export function useSkillCopyCompare(uid: string, agentUid: string | null) {
  return useQuery({
    queryKey: skillCopyKey(uid, agentUid ?? ""),
    queryFn: () => skillsApi.compareCopy(uid, agentUid as string),
    enabled: !!uid && !!agentUid,
    retry: false,
  });
}

/** Keep master or the agent's version. No toast: the dialog shows a refusal
 *  and stays open on it. */
export function useResolveSkillCopy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; agentUid: string; keep: "master" | "agent" }) =>
      skillsApi.resolveCopy(vars.uid, vars.agentUid, vars.keep),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
  });
}

export function useSkillOrphans() {
  return useQuery({
    queryKey: skillOrphansKey,
    queryFn: async () => (await skillsApi.orphans()).items,
  });
}

export function useAdoptSkillOrphan() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (name: string) => skillsApi.adoptOrphan(name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Move an orphan folder out of the store. No toast: the confirmation shows a
 *  refusal inline. */
export function useRemoveSkillOrphan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => skillsApi.removeOrphan(name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: skillsKey }),
  });
}

/** Write the Add dialog's "Available to" onto the skills it just added: every
 *  agent is what an add already did, so only Off and chosen agents write. */
export function useApplySkillReach() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async (vars: { uids: string[]; mode: ReachMode; scope: Scope | null }) => {
      for (const uid of vars.uids) {
        if (vars.mode === "disabled") await resourcesApi.disable(uid);
        else if (vars.mode === "restricted" && vars.scope) await scopeApi.put(uid, vars.scope);
      }
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: skillsKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: scopeKey });
    },
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** Stage a new source for a Git skill. No toast: the dialog renders why the
 *  source can't be used (unreachable, another skill's name). */
export function useChangeSkillSource() {
  return useMutation({
    mutationFn: (vars: { uid: string; url: string; ref: string | null; path: string | null }) =>
      skillsApi.changeSource(vars.uid, { url: vars.url, ref: vars.ref, path: vars.path }),
  });
}

/** An orphan folder's file tree, read-only (same shape as a skill's Files tab). */
export function useSkillOrphanFiles(name: string) {
  return useQuery({
    queryKey: skillOrphanFilesKey(name),
    queryFn: async () => (await skillsApi.orphanFiles(name)).root,
    enabled: !!name,
  });
}

/** One file of an orphan folder. */
export function useSkillOrphanFileContent(name: string, path: string | null) {
  return useQuery({
    queryKey: skillOrphanFileKey(name, path ?? ""),
    queryFn: () => skillsApi.orphanFileContent(name, path as string),
    enabled: !!name && !!path,
  });
}
