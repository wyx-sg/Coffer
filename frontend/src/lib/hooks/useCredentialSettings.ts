// frontend/src/lib/hooks/useCredentialSettings.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type CredentialSettingsOut = components["schemas"]["CredentialSettingsOut"];
type CredentialSettingsIn = components["schemas"]["CredentialSettingsIn"];

export function useCredentialSettings() {
  return useQuery({
    queryKey: ["credential-settings"],
    queryFn: async (): Promise<CredentialSettingsOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/settings/credentials");
      if (error) throwApiError(error, "INTERNAL_ERROR", "get credential settings failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty credential settings response");
      return data;
    },
  });
}

export function useUpdateCredentialSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CredentialSettingsIn): Promise<CredentialSettingsOut> => {
      const client = getApiClient();
      const { data, error } = await client.PUT("/settings/credentials", { body });
      if (error) throwApiError(error, "INTERNAL_ERROR", "update credential settings failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty credential settings response");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["credential-settings"] });
    },
  });
}
