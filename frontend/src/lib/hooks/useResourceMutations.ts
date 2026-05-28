// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateApiError } from "@/lib/api/errors";
import { resourcesApi } from "@/lib/api/resources";
import { useToast } from "@/components/ui/toast";

interface EnableDisableInput {
  kind: string;
  name: string;
}

export function useEnableResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.enable(kind, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDisableResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.disable(kind, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDeleteResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.remove(kind, name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
