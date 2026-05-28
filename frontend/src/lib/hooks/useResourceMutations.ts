// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

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
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "enable failed",
        );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resources"] });
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
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "disable failed",
        );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resources"] });
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
      if (error)
        throw new ApiError(
          error.error?.code ?? "INTERNAL_ERROR",
          error.error?.message ?? "delete failed",
        );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resources"] });
    },
  });
}
