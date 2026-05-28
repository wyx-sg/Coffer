// frontend/src/lib/api/resources.ts
// Thin typed wrappers around the kind-agnostic resource enable/disable/delete
// endpoints. Shared by the per-row mutation hooks (useResourceMutations) and the
// bulk fan-out (McpServersBulkActions via useBulkMutate) so both hit the same
// request with one source of truth; each throws an ApiError on a non-2xx body.
import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";

export const resourcesApi = {
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
