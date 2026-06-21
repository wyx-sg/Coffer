// frontend/src/lib/hooks/useProviders.ts — TanStack Query bindings for providers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { providersApi, type ProviderCreate } from "@/lib/api/providers";
import { useToast } from "@/components/ui/toast";

const PROVIDERS_KEY = ["providers"] as const;

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useProviderToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: async () => (await providersApi.list()).providers,
  });
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderCreate) => providersApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (name: string) => providersApi.remove(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
    onError,
  });
}

export function useActivateProvider() {
  const qc = useQueryClient();
  // Switching writes native config; a failure (e.g. unwritable config dir)
  // must surface rather than silently leave the old provider active.
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (name: string) => providersApi.activate(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROVIDERS_KEY });
    },
    onError,
  });
}
