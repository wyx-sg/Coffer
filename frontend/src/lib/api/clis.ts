// src/lib/api/clis.ts — request functions for /api/v1/clis (the command-line tools: required by skills or MCP servers, or added by hand).
//
// Every wire type is an alias of the skill-manager contract's generated
// schemas (`surfaces/http/cli_schemas.py`, `cli_interface_schemas.py`). A tool
// is addressed by its bare command name. The daemon only detects: a command
// that needs the person carries a `handoff` prompt for their agent, and
// nothing here installs or logs in. Reading a tool's interface (POST
// `…/interface`) runs only its `--help`; a GET never runs it.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/types";

type Schemas = components["schemas"];

export type Cli = Schemas["CliOut"];
export type CliList = Schemas["CliListOut"];
export type CliWarning = Schemas["CliWarningOut"];
export type CliStatus = Cli["status"];
export type CliAddInput = Schemas["CliAddIn"];
export type CliEditInput = Schemas["CliEditIn"];
export type CliPreview = Schemas["CliPreviewOut"];
export type CliInterface = Schemas["CliInterfaceOut"];
export type CliHelpNode = Schemas["CliHelpNodeOut"];
export type CliHelpOption = Schemas["CliHelpOptionOut"];

const one = (command: string) => ({ params: { path: { command } } });

export const clisApi = {
  /** Every command-line tool, problems first (the server's order). */
  list: () => unwrap(getApiClient().GET("/clis")),
  /** Probe every command again. */
  checkAll: () => unwrap(getApiClient().POST("/clis/check")),
  get: (command: string) => unwrap(getApiClient().GET("/clis/{command}", one(command))),
  /** Add a tool by hand, with no skill. */
  add: (body: CliAddInput) => unwrap(getApiClient().POST("/clis", { body })),
  /** What Coffer finds for a name or path, before anything is saved. */
  preview: (command: string) => unwrap(getApiClient().POST("/clis/preview", { body: { command } })),
  /** Change a tool added by hand; a field left out stays, `null` clears it. */
  edit: (command: string, body: CliEditInput) =>
    unwrap(getApiClient().PATCH("/clis/{command}", { ...one(command), body })),
  /** Drop the hand-added declaration (a skill that requires it keeps it listed). */
  remove: (command: string) => unwrapVoid(getApiClient().DELETE("/clis/{command}", one(command))),
  /** The interface as kept for this version of the tool; never runs it. */
  interface: (command: string) =>
    unwrap(getApiClient().GET("/clis/{command}/interface", one(command))),
  /** Run the tool's help again and keep the tree (can take ~30 s). */
  readInterface: (command: string) =>
    unwrap(getApiClient().POST("/clis/{command}/interface", one(command))),
};
