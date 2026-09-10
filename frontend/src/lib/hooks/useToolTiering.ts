// frontend/src/lib/hooks/useToolTiering.ts
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type ToolTieringOut = components["schemas"]["ToolTieringOut"];

/**
 * How much of the aggregated tool catalogue agents currently see (ADR budget-driven-tool-tiering).
 *
 * Global, not per server: the listing budget is shared, so a server whose tools
 * all fit locally can still be crowded out of what agents are shown.
 */
export function useToolTiering(enabled: boolean = true) {
  return useQuery({
    queryKey: ["mcp", "tiering"],
    queryFn: async (): Promise<ToolTieringOut> => {
      const client = getApiClient();
      const { data, error } = await client.GET("/mcp/tiering", {});
      if (error) throwApiError(error, "UPSTREAM_UNAVAILABLE", "load tool tiering failed");
      if (!data) throw new ApiError("UPSTREAM_UNAVAILABLE", "empty tiering response");
      return data;
    },
    enabled,
    staleTime: 30_000,
  });
}
