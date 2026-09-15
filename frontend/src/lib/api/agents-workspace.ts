// frontend/src/lib/api/agents-workspace.ts — wire types for the agent workspace
// surfaces (MCP entries, plugins, unmanaged skills). Split out of agents.ts for
// the file-size budget; re-exported there so existing import paths keep working.
//
// MCP entries and plugins are the agent-registry contract's generated schemas
// under the names the hooks already import. Unmanaged skills stay hand-written:
// they belong to the skill-manager contract, which does not generate (it
// `$ref`s a schema it never defines — see `scripts/codegen.mjs`).
import type { components } from "@/lib/api/generated/agent-registry";

type Schemas = components["schemas"];

export type McpEntryOut = Schemas["McpEntry"];

export type McpEntriesResponse = Schemas["McpEntriesOut"];

export type AdoptMcpEntryBody = Schemas["McpEntryAdopt"];

/** `version` … `mcp_servers`: best-effort detail read from the plugin's
 * install dir (Claude only today; null / empty otherwise). */
export type PluginOut = Schemas["Plugin"];

export type MarketplaceOut = Schemas["Marketplace"];

/** `can_uninstall`: whether in-app uninstall is available for this agent now
 * (capability +, for CLI-strategy agents like Claude, the agent's CLI being on
 * PATH). */
export type PluginsResponse = Schemas["PluginsOut"];

export interface UnmanagedSkillOut {
  name: string;
  path: string;
  location: string;
  valid: boolean;
  reason: string | null;
  foreign_link: boolean;
}

export interface UnmanagedSkillsResponse {
  items: UnmanagedSkillOut[];
}
