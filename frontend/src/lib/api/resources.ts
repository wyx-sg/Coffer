// frontend/src/lib/api/resources.ts
// Thin typed wrappers around the kind-agnostic resource enable/disable/delete
// endpoints. Shared by the per-row mutation hooks (useResourceMutations) and the
// bulk fan-out (McpServersBulkActions via useBulkMutate) so both hit the same
// request with one source of truth; each throws an ApiError on a non-2xx body.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

/** One row of the kind-agnostic resource list (`GET /resources`). */
export type ResourceOut = components["schemas"]["ResourceOut"];

/** `POST /resources` body — what registering any kind takes. */
export type ResourceCreate = components["schemas"]["ResourceCreate"];
/** `PATCH /resources/{kind}/{name}` body — description and/or config. */
export type ResourceUpdate = components["schemas"]["ResourceUpdate"];

export const resourcesApi = {
  /** Register a resource of any kind whose create the framework allows
   *  generically (a workflow template is one — FR-056: the editor writes
   *  through this endpoint and has no write path of its own). The refusal is
   *  thrown as-is so a caller can read the offending field's JSON path out of
   *  it (FR-055). */
  create: async (body: ResourceCreate): Promise<void> => {
    const { error } = await getApiClient().POST("/resources", { body });
    if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
  },
  update: async (kind: string, name: string, body: ResourceUpdate): Promise<void> => {
    const { error } = await getApiClient().PATCH("/resources/{kind}/{name}", {
      params: { path: { kind, name } },
      body,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
  },
  enable: async (kind: string, name: string): Promise<void> => {
    const { error } = await getApiClient().POST("/resources/{kind}/{name}/enable", {
      params: { path: { kind, name } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "enable failed");
  },
  disable: async (kind: string, name: string): Promise<void> => {
    const { error } = await getApiClient().POST("/resources/{kind}/{name}/disable", {
      params: { path: { kind, name } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "disable failed");
  },
  remove: async (kind: string, name: string): Promise<void> => {
    const { error } = await getApiClient().DELETE("/resources/{kind}/{name}", {
      params: { path: { kind, name } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "delete failed");
  },
};
