// src/lib/api/resourceList.ts — request functions for the generic resource list and one resource by uid.
import { getApiClient, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

export type ResourceOut = components["schemas"]["ResourceOut"];

export const resourceListApi = {
  list: async (kind?: string): Promise<ResourceOut[]> =>
    (await unwrap(getApiClient().GET("/resources", { params: { query: kind ? { kind } : {} } })))
      .resources,
  get: (uid: string): Promise<ResourceOut> =>
    unwrap(getApiClient().GET("/resources/{uid}", { params: { path: { uid } } })),
};
