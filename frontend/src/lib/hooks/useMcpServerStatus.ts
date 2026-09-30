// frontend/src/lib/hooks/useMcpServerStatus.ts
//
// ONE query per server over `/status`, read two ways. The health cell and the
// missing-runner note used to be two hooks with two keys over the same
// endpoint, so the list page fetched `/status` twice per row; both now `select`
// their slice out of a single cached read.
import { useQuery } from "@tanstack/react-query";
import { getApiClient } from "@/lib/api/client";
import { mcpStatusKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";

type McpServerStatus = "healthy" | "failing";
/** The status read's explanation fields (last error, since when, missing secret…). */
export type McpStatusDetail = components["schemas"]["McpServerStatusOut"];

interface ServerStatusRead {
  /** `null` = nothing known yet, so the card shows no badge. */
  status: McpServerStatus | null;
  /** The stdio launcher missing on THIS machine, if any. */
  missingRunner: string | null;
  /** The whole answer, for the server page; null when the read failed. */
  detail: McpStatusDetail | null;
}

/** A cheap backend read of persisted state (discovered capabilities + last
 * invocation), no subprocess spawn. An API error degrades to "nothing known". */
export async function readServerStatus(serverUid: string): Promise<ServerStatusRead> {
  const client = getApiClient();
  const { data, error } = await client.GET("/resources/mcp_server/{uid}/status", {
    params: { path: { uid: serverUid } },
  });
  if (error || !data) return { status: null, missingRunner: null, detail: null };
  return {
    status: data.status === "unknown" ? null : data.status,
    missingRunner: data.missing_runner ?? null,
    detail: data,
  };
}

function useServerStatusRead<T>(serverUid: string, select: (read: ServerStatusRead) => T) {
  return useQuery({
    queryKey: mcpStatusKey(serverUid),
    queryFn: () => readServerStatus(serverUid),
    select,
    // The detail page knows the uid only once the name has resolved.
    enabled: serverUid.length > 0,
  });
}

// Module-level selectors keep a stable identity, so `select` is not re-run on
// every render of every row.
const selectStatus = (read: ServerStatusRead) => read.status;
const selectRunner = (read: ServerStatusRead) => ({ missingRunner: read.missingRunner });
const selectDetail = (read: ServerStatusRead) => read.detail;

/** Card-level health of a server; `null` = nothing known yet. */
export function useMcpServerStatus(serverUid: string) {
  return useServerStatusRead(serverUid, selectStatus);
}

/** The stdio launcher missing on THIS machine (imported server, runner not
 * installed here), if any — rendered as "missing <runner>" with a hint to
 * install it manually. Coffer manages configuration; it does not install
 * software on the user's machine. */
export function useMcpServerRunner(serverUid: string) {
  return useServerStatusRead(serverUid, selectRunner);
}

/** The whole status answer — what the server page and the list's reasons are
 *  written from; `null` when the read failed. */
export function useMcpServerStatusDetail(serverUid: string) {
  return useServerStatusRead(serverUid, selectDetail);
}
