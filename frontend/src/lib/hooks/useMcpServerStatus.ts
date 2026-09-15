// frontend/src/lib/hooks/useMcpServerStatus.ts
//
// ONE query per server over `/status`, read two ways. The health cell and the
// missing-runner note used to be two hooks with two keys over the same
// endpoint, so the list page fetched `/status` twice per row; both now `select`
// their slice out of a single cached read.
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { mcpStatusKey } from "@/lib/api/queryKeys";

export type McpServerStatus = "healthy" | "failing";

interface ServerStatusRead {
  /** `null` = nothing known yet, so the card shows no badge. */
  status: McpServerStatus | null;
  /** The stdio launcher missing on THIS machine, if any. */
  missingRunner: string | null;
}

/** A cheap backend read of persisted state (discovered capabilities + last
 * invocation), no subprocess spawn. An API error degrades to "nothing known". */
async function readServerStatus(serverName: string): Promise<ServerStatusRead> {
  const client = getApiClient();
  const { data, error } = await client.GET("/resources/mcp_server/{name}/status", {
    params: { path: { name: serverName } },
  });
  if (error || !data) return { status: null, missingRunner: null };
  return {
    status: data.status === "unknown" ? null : data.status,
    missingRunner: data.missing_runner ?? null,
  };
}

function useServerStatusRead<T>(serverName: string, select: (read: ServerStatusRead) => T) {
  return useQuery({
    queryKey: mcpStatusKey(serverName),
    queryFn: () => readServerStatus(serverName),
    select,
  });
}

// Module-level selectors keep a stable identity, so `select` is not re-run on
// every render of every row.
const selectStatus = (read: ServerStatusRead) => read.status;
const selectRunner = (read: ServerStatusRead) => ({ missingRunner: read.missingRunner });

/** Card-level health of a server; `null` = nothing known yet. */
export function useMcpServerStatus(serverName: string) {
  return useServerStatusRead(serverName, selectStatus);
}

/** The stdio launcher missing on THIS machine (imported server, runner not
 * installed here), if any — rendered as "missing <runner>" with a hint to
 * install it manually. Coffer manages configuration; it does not install
 * software on the user's machine. */
export function useMcpServerRunner(serverName: string) {
  return useServerStatusRead(serverName, selectRunner);
}
