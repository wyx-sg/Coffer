// frontend/src/lib/hooks/useSecretSettings.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { secretSettingsApi } from "@/lib/api/settingsSecrets";
import { secretSettingsKey } from "@/lib/api/queryKeys";

export function useSecretSettings() {
  return useQuery({
    queryKey: secretSettingsKey,
    queryFn: secretSettingsApi.get,
  });
}

export function useUpdateSecretSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: secretSettingsApi.update,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: secretSettingsKey });
    },
  });
}
