// frontend/src/lib/hooks/useMcpCapabilities.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

export function useMcpCapabilities(serverName: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ["mcp", "capabilities", serverName],
    queryFn: async (): Promise<CapabilityListOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{name}/capabilities", {
        params: { path: { name: serverName } },
      });
      if (error) throwApiError(error, "UPSTREAM_UNAVAILABLE", "list capabilities failed");
      if (!data) throw new ApiError("UPSTREAM_UNAVAILABLE", "empty capability response");
      return data;
    },
    enabled,
    staleTime: 30_000,
  });
}
