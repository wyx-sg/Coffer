// frontend/src/lib/hooks/useMcpCapabilities.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

export function useMcpCapabilities(serverUid: string, enabled: boolean = true) {
  return useQuery({
    queryKey: mcpCapabilitiesKey(serverUid),
    queryFn: async (): Promise<CapabilityListOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{uid}/capabilities", {
        params: { path: { uid: serverUid } },
      });
      if (error) throwApiError(error, "UPSTREAM_UNAVAILABLE", "list capabilities failed");
      if (!data) throw new ApiError("UPSTREAM_UNAVAILABLE", "empty capability response");
      return data;
    },
    enabled,
    staleTime: 30_000,
  });
}
