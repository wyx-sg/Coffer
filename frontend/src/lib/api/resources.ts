// frontend/src/lib/api/resources.ts
// Thin typed wrappers around the kind-agnostic resource enable/disable/rename/
// delete endpoints. Shared by the per-row mutation hooks (useResourceMutations)
// and the bulk fan-out (McpServersBulkActions via useBulkMutate) so both hit the
// same request with one source of truth; each throws an ApiError on a non-2xx
// body.
//
// Every route here is addressed by the resource's `uid` and NOT by its kind and
// name. The kind segment is gone because a uid already names exactly one row,
// and the name is gone because it is a label the user edits — a request built
// from it would stop resolving the moment someone renamed the thing it was
// about (ADR resource-identity-is-an-immutable-uid).
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

/** One row of the kind-agnostic resource list (`GET /resources`). */
export type ResourceOut = components["schemas"]["ResourceOut"];

/** `POST /resources` body — what registering any kind takes. */
export type ResourceCreate = components["schemas"]["ResourceCreate"];
/** `PATCH /resources/{uid}` body — name, description and/or config. */
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
  update: async (uid: string, body: ResourceUpdate): Promise<void> => {
    const { error } = await getApiClient().PATCH("/resources/{uid}", {
      params: { path: { uid } },
      body,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
  },
  enable: async (uid: string): Promise<void> => {
    const { error } = await getApiClient().POST("/resources/{uid}/enable", {
      params: { path: { uid } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "enable failed");
  },
  disable: async (uid: string): Promise<void> => {
    const { error } = await getApiClient().POST("/resources/{uid}/disable", {
      params: { path: { uid } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "disable failed");
  },
  remove: async (uid: string): Promise<void> => {
    const { error } = await getApiClient().DELETE("/resources/{uid}", {
      params: { path: { uid } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "delete failed");
  },
  /**
   * Rename a resource of ANY kind.
   *
   * A rename is an ordinary field edit, not an operation: it is the same PATCH
   * that changes a description, and it is the same route for every kind. The
   * `provider` kind used to own a `POST /providers/{name}/rename` of its own,
   * which existed only because the name was the identity and so moving it had
   * to be a deliberate act; with the uid carrying identity there is nothing
   * left for that route to do.
   *
   * A label another resource of the same kind already holds answers 409, which
   * the caller renders where the user typed it.
   */
  rename: async (uid: string, name: string): Promise<ResourceOut> => {
    const { data, error } = await getApiClient().PATCH("/resources/{uid}", {
      params: { path: { uid } },
      body: { name },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "rename failed");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty rename response");
    return data;
  },
};
