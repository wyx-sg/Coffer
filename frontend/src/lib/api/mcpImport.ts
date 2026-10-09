// frontend/src/lib/api/mcpImport.ts — import agents' direct MCP entries into
// Coffer (spec agent-registry "Plan an import of agents' direct MCP entries").
//
// `plan` writes nothing: servers to add / merge / already in Coffer, and a
// redacted per-file diff of each agent config file.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

export type McpImportEntryIn = components["schemas"]["McpImportEntryIn"];
export type McpImportPlan = components["schemas"]["McpImportPlanOut"];

export const mcpImportApi = {
  plan: async (entries: McpImportEntryIn[]): Promise<McpImportPlan> => {
    const { data, error } = await getApiClient().POST("/agents/mcp-import/plan", {
      body: { entries },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "import plan failed");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty import plan");
    return data;
  },
};
