// frontend/src/lib/hooks/useDaemonResidency.ts
//
// Whether the daemon outlives the things that use it (spec daemon FR-028) and
// for how long it stays once nothing does (FR-029). One route, because they
// are one question with two halves — see the contract.
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
    // service may have refused, and the idle window it reports is the one the
    // next start will read. Seed the cache from that rather than from what
    // was asked for.
    onSuccess: (fresh) => qc.setQueryData(daemonResidencyKey, fresh),
  });
}
