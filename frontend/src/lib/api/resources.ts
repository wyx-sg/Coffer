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
// about (ADR identity-is-the-uid-inside-the-file).
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

/** One row of the kind-agnostic resource list (`GET /resources`). */
export type ResourceOut = components["schemas"]["ResourceOut"];

/** `POST /resources` body — what registering any kind takes. */
export type ResourceCreate = components["schemas"]["ResourceCreate"];
/** `PATCH /resources/{uid}` body — name, title, description and/or config. */
export type ResourceUpdate = components["schemas"]["ResourceUpdate"];

/** `GET /resources` — every resource, or those of one kind. */
export type ResourceList = components["schemas"]["ResourceListOut"];

export const resourcesApi = {
  /** The resources of one kind. A failed read throws, so a caller that picks a
   *  name from the answer never picks one against an empty list it misread. */
  list: (kind: string): Promise<ResourceList> =>
    unwrap(getApiClient().GET("/resources", { params: { query: { kind } } })),
  /** Register a resource of any kind whose create the framework allows
   *  generically, so a kind with no bespoke registration surface of its own
   *  writes through this endpoint. The refusal is thrown as-is so a caller can
   *  read the offending field's JSON path out of it. */
  create: (body: ResourceCreate): Promise<ResourceOut> =>
    unwrap(getApiClient().POST("/resources", { body })),
  update: (uid: string, body: ResourceUpdate): Promise<void> =>
    unwrapVoid(getApiClient().PATCH("/resources/{uid}", { params: { path: { uid } }, body })),
  enable: (uid: string): Promise<void> =>
    unwrapVoid(getApiClient().POST("/resources/{uid}/enable", { params: { path: { uid } } })),
  disable: (uid: string): Promise<void> =>
    unwrapVoid(getApiClient().POST("/resources/{uid}/disable", { params: { path: { uid } } })),
  remove: (uid: string): Promise<void> =>
    unwrapVoid(getApiClient().DELETE("/resources/{uid}", { params: { path: { uid } } })),
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
  rename: (uid: string, name: string): Promise<ResourceOut> =>
    unwrap(getApiClient().PATCH("/resources/{uid}", { params: { path: { uid } }, body: { name } })),
};
