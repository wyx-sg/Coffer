// frontend/src/lib/api/mcpTestConfig.ts — test an MCP server config before it
// is added (spec mcp-gateway "Test an unsaved server config before adding it").
//
// The daemon starts or reaches the server for the length of the test and
// persists nothing. A failed test is NOT an HTTP error: it is a 200 with
// `ok: false` and an `error_code`; only a malformed config (422) or a daemon
// failure throws.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

/** What the Add form sends: a config as it would register, plus typed secrets. */
export type McpConfigTestIn = components["schemas"]["McpConfigTestIn"];
/** What a test found — the same shape a registered server's test answers. */
export type McpTestResult = components["schemas"]["McpTestResultOut"];
/** Why a test failed. */

export const mcpTestConfigApi = {
  test: async (body: McpConfigTestIn, signal?: AbortSignal): Promise<McpTestResult> => {
    const { data, error } = await getApiClient().POST("/resources/mcp_server/test-config", {
      body,
      signal,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "test failed");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty test response");
    return data;
  },
};
