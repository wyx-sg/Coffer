// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

interface EnableDisableInput {
  kind: string;
  name: string;
}

export function useEnableResource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, name }: EnableDisableInput) => {
      const client = getApiClient();
      const { error } = await client.POST("/resources/{kind}/{name}/enable", {
        params: { path: { kind, name } },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "enable failed");
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
  });
}

export function useDisableResource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, name }: EnableDisableInput) => {
      const client = getApiClient();
      const { error } = await client.POST("/resources/{kind}/{name}/disable", {
        params: { path: { kind, name } },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "disable failed");
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
  });
}

export function useDeleteResource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, name }: EnableDisableInput) => {
      const client = getApiClient();
      const { error } = await client.DELETE("/resources/{kind}/{name}", {
        params: { path: { kind, name } },
      });
      if (error) throwApiError(error, "INTERNAL_ERROR", "delete failed");
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
    },
  });
}
