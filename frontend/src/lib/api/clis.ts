// src/lib/api/clis.ts — request functions for /api/v1/clis (the commands managed skills require).
//
// Every wire type is an alias of the skill-manager contract's generated
// schemas (`surfaces/http/cli_schemas.py`). A command is addressed by its bare
// name — it is the row's identity, fixed by the skills that declare it. The
// daemon only detects: a command that needs the person carries a `handoff`
// prompt for their agent, and nothing here installs or logs in.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type Cli = Schemas["CliOut"];
export type CliList = Schemas["CliListOut"];
export type CliWarning = Schemas["CliWarningOut"];
export type CliStatus = Cli["status"];

function must<T>(data: T | undefined, what: string): T {
  if (data === undefined) throw new ApiError("INTERNAL_ERROR", `empty ${what} response`);
  return data;
}

const one = (command: string) => ({ params: { path: { command } } });

export const clisApi = {
  /** Every required command, problems first (the server's order). */
  list: async (): Promise<CliList> => {
    const { data, error } = await getApiClient().GET("/clis");
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to list CLIs");
    return must(data, "list");
  },
  /** Probe every required command again. */
  checkAll: async (): Promise<CliList> => {
    const { data, error } = await getApiClient().POST("/clis/check");
    if (error) throwApiError(error, "INTERNAL_ERROR", "check failed");
    return must(data, "check");
  },
  get: async (command: string): Promise<Cli> => {
    const { data, error } = await getApiClient().GET("/clis/{command}", one(command));
    if (error) throwApiError(error, "CLI_NOT_REQUIRED", "no skill requires this command");
    return must(data, "cli");
  },
};
