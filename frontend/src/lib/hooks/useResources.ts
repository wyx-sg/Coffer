// frontend/src/lib/hooks/useResources.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type ResourceOut = components["schemas"]["ResourceOut"];

export function useResources(kind?: string) {
  return useQuery({
    queryKey: ["resources", { kind }],
    queryFn: async (): Promise<ResourceOut[]> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources", {
        params: { query: kind ? { kind } : {} },
      });
      if (error)
        throwApiError(error, "INTERNAL_ERROR", `failed to list resources: ${kind ?? "all"}`);
      return data?.resources ?? [];
    },
  });
}

export function useResource(kind: string, name: string) {
  return useQuery({
    queryKey: ["resources", kind, name],
    queryFn: async (): Promise<ResourceOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/{kind}/{name}", {
        params: { path: { kind, name } },
      });
      if (error) throwApiError(error, "RESOURCE_NOT_FOUND", "resource not found");
      if (!data) throw new ApiError("RESOURCE_NOT_FOUND", "empty resource response");
      return data;
    },
  });
}
