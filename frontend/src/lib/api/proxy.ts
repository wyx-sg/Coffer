// frontend/src/lib/api/proxy.ts — request helpers for /api/v1/proxy/* (the local model proxy).
//
// Types alias the provider-switching contract's generated schemas.
import { call, enc } from "@/lib/api/call";
import type { components } from "@/lib/api/generated/provider-switching";

type Schemas = components["schemas"];

/** An agent's provider and the providers tried next, in list order. */
export type ProxyRoute = Schemas["ProxyRouteOut"];
export type ProxyTokenHint = Schemas["ProxyTokenHintOut"];

export type ProxyStatus = Schemas["ProxyStatusOut"];

/** The proxy's loopback address the agents are pointed at. */
export const proxyAddress = (port: number | undefined) => `127.0.0.1:${port ?? 8001}`;

// Query keys for the proxy's reads (kept here: queryKeys.ts is at its size limit).
export const proxyRouteKey = (agentUid: string, model: string | null) =>
  ["proxy", "route", agentUid, model] as const;
export const proxyStatusKey = ["proxy", "status"] as const;
export const proxyTokenHintKey = (agentUid: string) => ["proxy", "token", agentUid] as const;

export const proxyApi = {
  status: () => call<ProxyStatus>("/proxy/status"),
  route: (agentUid: string, model: string | null) =>
    call<ProxyRoute>(
      `/proxy/routes/${enc(agentUid)}${model ? `?model=${encodeURIComponent(model)}` : ""}`,
    ),
  tokenHint: (agentUid: string) => call<ProxyTokenHint>(`/proxy/tokens/${enc(agentUid)}/hint`),
  rotateToken: (agentUid: string) =>
    call<{ agent_uid: string; rotated: boolean }>(`/proxy/tokens/${enc(agentUid)}/rotate`, {
      method: "POST",
    }),
};
