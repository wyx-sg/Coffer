// frontend/src/lib/hooks/useMachines.ts
//
// The machine registry (spec vault-sync "Derive the registry from the
// descriptors"): every installation of Coffer that has converged with this
// remote, read as a derived view of `machines/*.yaml` in the working tree.
//
// The list is not only the Machines tab's data — it is also the pick-list the
// channel binding control offers (spec channels, "Bind each channel to the one machine that runs it"),
// which is why it lives in its own hook file rather than inside the Sync
// page's tree. `scope` has no machine axis and never did name a machine; the
// binding does, by DERIVED id rather than display name, so renaming a machine
// is free and a mistyped id can never be entered by hand.
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
 * Rename THIS machine. Free by construction: a channel's binding references
 * the derived id, never the label, so nothing else has to change.
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
 * Retire another machine: its descriptor leaves the registry, and nothing in
 * the vault is rewritten to match. Reach is set per machine and names no
 * machine id, so there is nothing to strip out of it.
 *
 * A channel BOUND to the retired machine keeps its binding, and that is the
 * honest outcome rather than an oversight: the channel now names a machine
 * nobody claims, which means it runs nowhere and needs a rebind — a fault the
 * channel surfaces report. Silently unbinding it would swap one dead state for
 * another and lose the evidence of which machine it used to be. The resource
 * caches are still invalidated, because those surfaces now read differently.
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
