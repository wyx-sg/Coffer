// frontend/src/lib/hooks/useDaemonResidency.ts
//
// Whether the daemon outlives the things that use it (spec daemon "Run as a
// login service"). Nothing ends it on its own, so there is no idle window to
// read or write — see the contract.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { daemonResidencyKey } from "@/lib/api/queryKeys";

export type DaemonResidency = components["schemas"]["DaemonResidencyOut"];
export type DaemonResidencyIn = components["schemas"]["DaemonResidencyIn"];

export function useDaemonResidency() {
  return useQuery({
    queryKey: daemonResidencyKey,
    queryFn: async (): Promise<DaemonResidency> => {
      const { data, error } = await getApiClient().GET("/daemon/residency");
      if (error) throwApiError(error, "INTERNAL_ERROR", "residency failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty residency response");
      return data;
    },
  });
}

export function useSetDaemonResidency() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: DaemonResidencyIn): Promise<DaemonResidency> => {
      const { data, error } = await getApiClient().PUT("/daemon/residency", { body });
      if (error) throwApiError(error, "INTERNAL_ERROR", "residency update failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty residency response");
      return data;
    },
    // The daemon answers with what is true AFTER the change — the login
    // service may have refused. Seed the cache from that rather than from
    // what was asked for.
    onSuccess: (fresh) => qc.setQueryData(daemonResidencyKey, fresh),
  });
}
