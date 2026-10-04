// frontend/src/lib/hooks/useMcpCapabilities.ts — one server's tools, resources and prompts.
//
// Live by default. `saved` answers from the saved switches without reaching
// the server — what a failing, off or unreachable server's page shows at once
// instead of waiting out the discovery timeout.
import { useQuery } from "@tanstack/react-query";
import { mcpServersApi, type CapabilityList } from "@/lib/api/mcpServers";
import { mcpCapabilitiesKey } from "@/lib/api/queryKeys";

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
    queryFn: (): Promise<CapabilityList> => mcpServersApi.capabilities(serverUid, saved),
    enabled,
    staleTime: 30_000,
  });
}
