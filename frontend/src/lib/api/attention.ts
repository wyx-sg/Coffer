// src/lib/api/attention.ts — request functions for the cross-kind "needs you" list.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type AttentionReport = components["schemas"]["AttentionOut"];
export type AttentionItem = components["schemas"]["AttentionItemOut"];

export const attentionApi = {
  read: (): Promise<AttentionReport> => unwrap(getApiClient().GET("/attention")),
  ignore: (key: string): Promise<void> =>
    unwrapVoid(getApiClient().PUT("/attention/ignored/{key}", { params: { path: { key } } })),
};
