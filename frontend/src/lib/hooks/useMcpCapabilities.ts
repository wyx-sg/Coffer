// frontend/src/lib/hooks/useMcpCapabilities.ts — one server's tools, resources and prompts.
//
// Live by default. `saved` answers from the saved switches without reaching
// the server — what a failing, off or unreachable server's page shows at once
// instead of waiting out the discovery timeout.
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";

type CapabilityListOut = components["schemas"]["CapabilityListOut"];

interface Options {
  enabled?: boolean;
  /** Read the saved switches only (`?saved=true`). */
  saved?: boolean;
}

export function useMcpCapabilities(serverUid: string, options: Options | boolean = {}) {
  const { enabled = true, saved = false } =
    typeof options === "boolean" ? { enabled: options } : options;
  return useQuery({
    // The saved read sits under the live key, so one invalidation catches both.
    queryKey: saved ? [...mcpCapabilitiesKey(serverUid), "saved"] : mcpCapabilitiesKey(serverUid),
    queryFn: async (): Promise<CapabilityListOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/resources/mcp_server/{uid}/capabilities", {
        params: { path: { uid: serverUid }, ...(saved ? { query: { saved: true } } : {}) },
      });
      if (error) throwApiError(error, "UPSTREAM_UNAVAILABLE", "list capabilities failed");
      if (!data) throw new ApiError("UPSTREAM_UNAVAILABLE", "empty capability response");
      return data;
    },
    enabled,
    staleTime: 30_000,
  });
}
