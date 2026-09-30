// src/lib/api/customTools.ts — request functions for /api/v1/custom-tools (groups of HTTP API tools).
//
// Every wire type is an alias of the mcp-gateway contract's generated schemas,
// generated from `surfaces/http/mcp/custom_tool_schemas.py` (design
// add-http-custom-tools §9). A group is addressed by its fixed NAME; its
// enable/disable and reach go through the kind-agnostic resource routes by its
// uid (`lib/api/resources.ts`, `lib/api/scope.ts`). A group's secret travels by
// its Secrets-page name, never as a ref or a value.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type CustomToolGroup = Schemas["CustomToolGroupOut"];
export type CustomToolGroupIn = Schemas["CustomToolGroupIn"];
export type CustomToolGroupPatch = Schemas["CustomToolGroupPatch"];
export type CustomTool = Schemas["CustomToolOut"];
export type CustomToolIn = Schemas["CustomToolIn"];
export type CustomToolPatch = Schemas["CustomToolPatch"];
export type CustomToolAuthIn = Schemas["CustomToolAuthIn"];
export type CustomToolTestOut = Schemas["CustomToolTestOut"];
export type OpenApiReadIn = Schemas["OpenApiReadIn"];
export type OpenApiReading = Schemas["OpenApiReadOut"];
export type ReimportPreview = Schemas["CustomToolReimportPreviewOut"];
export type HttpMethod = CustomTool["method"];
export type GroupHealth = CustomToolGroup["health"];

/** Every method a tool may use, in the order the method select lists them. */
export const HTTP_METHODS: readonly HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

function must<T>(data: T | undefined, what: string): T {
  if (data === undefined) throw new ApiError("INTERNAL_ERROR", `empty ${what} response`);
  return data;
}

const group = (name: string) => ({ params: { path: { name } } });
const tool = (name: string, toolName: string) => ({
  params: { path: { name, tool: toolName } },
});

export const customToolsApi = {
  /** Every group, failing first. */
  list: async (): Promise<CustomToolGroup[]> => {
    const { data, error } = await getApiClient().GET("/custom-tools");
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to list custom tools");
    return must(data, "list").groups;
  },
  get: async (name: string): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().GET("/custom-tools/{name}", group(name));
    if (error) throwApiError(error, "CUSTOM_TOOL_NOT_FOUND", "custom tool group not found");
    return must(data, "group");
  },
  create: async (body: CustomToolGroupIn): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().POST("/custom-tools", { body });
    if (error) throwApiError(error, "INTERNAL_ERROR", "create failed");
    return must(data, "create");
  },
  update: async (name: string, body: CustomToolGroupPatch): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().PATCH("/custom-tools/{name}", {
      ...group(name),
      body,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "update failed");
    return must(data, "update");
  },
  remove: async (name: string): Promise<void> => {
    const { error } = await getApiClient().DELETE("/custom-tools/{name}", group(name));
    if (error) throwApiError(error, "INTERNAL_ERROR", "delete failed");
  },
  addTool: async (name: string, body: CustomToolIn): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().POST("/custom-tools/{name}/tools", {
      ...group(name),
      body,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "add tool failed");
    return must(data, "add tool");
  },
  updateTool: async (
    name: string,
    toolName: string,
    body: CustomToolPatch,
  ): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().PATCH("/custom-tools/{name}/tools/{tool}", {
      ...tool(name, toolName),
      body,
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "update tool failed");
    return must(data, "update tool");
  },
  removeTool: async (name: string, toolName: string): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().DELETE(
      "/custom-tools/{name}/tools/{tool}",
      tool(name, toolName),
    );
    if (error) throwApiError(error, "INTERNAL_ERROR", "delete tool failed");
    return must(data, "delete tool");
  },
  /** Set (`agents` = uids) or clear (`null`) one tool's reach override. */
  setToolReach: async (
    name: string,
    toolName: string,
    agents: string[] | null,
  ): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().PUT("/custom-tools/{name}/tools/{tool}/reach", {
      ...tool(name, toolName),
      body: { agents },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "reach failed");
    return must(data, "reach");
  },
  /** Run a draft tool once against the group's base URL and secret; saves nothing. */
  test: async (
    name: string,
    draft: CustomToolIn,
    args: Record<string, unknown>,
  ): Promise<CustomToolTestOut> => {
    const { data, error } = await getApiClient().POST("/custom-tools/{name}/test", {
      ...group(name),
      body: { tool: draft, arguments: args },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "test failed");
    return must(data, "test");
  },
  /** Read an OpenAPI document (by URL, or its text) into draft tools. */
  readOpenApi: async (body: OpenApiReadIn): Promise<OpenApiReading> => {
    const { data, error } = await getApiClient().POST("/custom-tools/openapi", { body });
    if (error) throwApiError(error, "OPENAPI_UNREADABLE", "the spec could not be read");
    return must(data, "openapi");
  },
  previewReimport: async (name: string, document?: string): Promise<ReimportPreview> => {
    const { data, error } = await getApiClient().POST("/custom-tools/{name}/reimport/preview", {
      ...group(name),
      body: document === undefined ? {} : { document },
    });
    if (error) throwApiError(error, "OPENAPI_UNREADABLE", "the spec could not be read");
    return must(data, "preview");
  },
  applyReimport: async (
    name: string,
    add: string[],
    document?: string,
  ): Promise<CustomToolGroup> => {
    const { data, error } = await getApiClient().POST("/custom-tools/{name}/reimport", {
      ...group(name),
      body: document === undefined ? { add } : { add, document },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "re-import failed");
    return must(data, "re-import");
  },
};
