// frontend/src/lib/hooks/useSecretSettings.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { secretSettingsKey } from "@/lib/api/queryKeys";

type SecretSettingsOut = components["schemas"]["SecretSettingsOut"];
type SecretSettingsIn = components["schemas"]["SecretSettingsIn"];

export function useSecretSettings() {
  return useQuery({
    queryKey: secretSettingsKey,
    queryFn: async (): Promise<SecretSettingsOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/settings/secrets");
      if (error) throwApiError(error, "INTERNAL_ERROR", "get secret settings failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty secret settings response");
      return data;
    },
  });
}

export function useUpdateSecretSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SecretSettingsIn): Promise<SecretSettingsOut> => {
      const client = getApiClient();
      const { data, error } = await client.PUT("/settings/secrets", { body });
      if (error) throwApiError(error, "INTERNAL_ERROR", "update secret settings failed");
      if (!data) throw new ApiError("INTERNAL_ERROR", "empty secret settings response");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: secretSettingsKey });
    },
  });
}
