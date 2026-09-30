// frontend/src/lib/api/mcpBuiltin.ts — Coffer's own `coffer` MCP server
// (spec mcp-gateway "Describe the built-in coffer server"). Read-only: it is
// not a registered resource, so no resource route addresses it. Its calls are
// in the invocation log under `invocation_uid` (`GET /mcp/invocations?uid=`).
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

export type McpBuiltinServer = components["schemas"]["McpBuiltinServerOut"];
export type McpBuiltinTool = components["schemas"]["BuiltinToolOut"];

export const mcpBuiltinApi = {
  get: async (): Promise<McpBuiltinServer> => {
    const { data, error } = await getApiClient().GET("/mcp/builtin");
    if (error) throwApiError(error, "INTERNAL_ERROR", "built-in server read failed");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty built-in server response");
    return data;
  },
};
