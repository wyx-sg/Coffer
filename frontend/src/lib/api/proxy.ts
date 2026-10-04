// frontend/src/lib/api/proxy.ts — request helpers for /api/v1/proxy/* (the local model proxy).
//
// Types alias the provider-switching contract's generated schemas.
import { getApiClient, unwrap } from "@/lib/api/client";

/** The proxy's loopback address the agents are pointed at. */
export const proxyAddress = (port: number | undefined) => `127.0.0.1:${port ?? 38471}`;

// Query keys for the proxy's reads (kept here: queryKeys.ts is at its size limit).
export const proxyStatusKey = ["proxy", "status"] as const;
export const proxyTokenHintKey = (agentUid: string) => ["proxy", "token", agentUid] as const;

export const proxyApi = {
  status: () => unwrap(getApiClient().GET("/proxy/status")),
  tokenHint: (agentUid: string) =>
    unwrap(
      getApiClient().GET("/proxy/tokens/{agent_uid}/hint", {
        params: { path: { agent_uid: agentUid } },
      }),
    ),
  rotateToken: (agentUid: string) =>
    unwrap(
      getApiClient().POST("/proxy/tokens/{agent_uid}/rotate", {
        params: { path: { agent_uid: agentUid } },
      }),
    ),
};
