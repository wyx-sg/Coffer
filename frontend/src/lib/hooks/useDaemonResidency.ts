// frontend/src/lib/hooks/useDaemonResidency.ts
//
// Whether the daemon outlives the things that use it (spec daemon "Run as a
// login service"). Nothing ends it on its own, so there is no idle window to
// read or write — see the contract.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { daemonApi } from "@/lib/api/daemon";
import { daemonResidencyKey } from "@/lib/api/queryKeys";

export function useDaemonResidency() {
  return useQuery({
    queryKey: daemonResidencyKey,
    queryFn: daemonApi.residency,
  });
}

export function useSetDaemonResidency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: daemonApi.setResidency,
    // The daemon answers with what is true AFTER the change — the login
    // service may have refused. Seed the cache from that rather than from
    // what was asked for.
    onSuccess: (fresh) => qc.setQueryData(daemonResidencyKey, fresh),
  });
}
