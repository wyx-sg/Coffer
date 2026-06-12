// frontend/src/lib/hooks/useModels.ts — TanStack Query bindings for models.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { modelsApi, type Model, type ModelCreate, type ModelPatch } from "@/lib/api/models";
import { useToast } from "@/components/ui/toast";

const MODELS_KEY = ["models"] as const;

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useModelToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

export function useModels() {
  return useQuery({
    queryKey: MODELS_KEY,
    queryFn: async () => (await modelsApi.list()).models,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ModelCreate) => modelsApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MODELS_KEY });
    },
  });
}

export function useUpdateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; patch: ModelPatch }) =>
      modelsApi.update(vars.id, vars.patch),
    onSuccess: (updated: Model) => {
      // Optimistically update the cached list entry.
      qc.setQueryData<Model[]>(MODELS_KEY, (prev) =>
        prev?.map((m) => (m.id === updated.id ? updated : m)),
      );
      qc.invalidateQueries({ queryKey: MODELS_KEY });
    },
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  // Delete has no inline form to surface its error (unlike create/update,
  // which render `submitError` in the ModelForm), so a failure must toast.
  const onError = useModelToastError();
  return useMutation({
    mutationFn: (id: string) => modelsApi.remove(id),
    onSuccess: (_data, id) => {
      qc.setQueryData<Model[]>(MODELS_KEY, (prev) =>
        prev?.filter((m) => m.id !== id),
      );
      qc.invalidateQueries({ queryKey: MODELS_KEY });
    },
    onError,
  });
}
