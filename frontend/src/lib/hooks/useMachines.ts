// frontend/src/lib/hooks/useMachines.ts
//
// The machine registry (spec vault-sync `## The machine dimension`): every
// installation of Coffer that has converged with this remote, read as a
// derived view of `machines/*.yaml` in the working tree.
//
// The list is not only the Machines tab's data — it is also the pick-list
// every scope editor builds its machine axis from, which is why it lives in
// its own hook file rather than inside the Sync page's tree. `scope` names a
// machine by its DERIVED id, never by the display name, so renaming is free
// and a mistyped id can never be entered by hand.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { syncApi } from "@/lib/api/sync";
import { useToast } from "@/components/ui/toast";
import { resourcesKey, scopeKey, skillsKey, syncKey, syncMachinesKey } from "@/lib/api/queryKeys";

export function useMachines() {
  return useQuery({ queryKey: syncMachinesKey, queryFn: () => syncApi.machines() });
}

/**
 * Rename THIS machine. Free by construction: `scope` references the derived
 * id, never the label, so nothing else has to change.
 */
export function useRenameSelf() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (name: string) => syncApi.renameSelf(name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: syncKey }),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Retire another machine. The daemon strips it from the scope of every
 * resource naming it in the same change — a descriptor removed while scopes
 * still name it would leave those resources dormant on a machine nobody can
 * see — so the resource caches are invalidated alongside the registry.
 */
export function useRetireMachine() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (machineId: string) => syncApi.retire(machineId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: syncKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
      void qc.invalidateQueries({ queryKey: skillsKey });
      void qc.invalidateQueries({ queryKey: scopeKey });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
