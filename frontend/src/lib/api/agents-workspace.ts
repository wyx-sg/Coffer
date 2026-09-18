// frontend/src/lib/api/agents-workspace.ts — wire types for the agent workspace
// surfaces (MCP entries, plugins, unmanaged skills). Split out of agents.ts for
// the file-size budget; re-exported there so existing import paths keep working.
//
// Every shape here is an alias of a generated schema under the name the hooks
// already import: MCP entries and plugins come from the agent-registry
// contract, the unmanaged-skill entry from the skill-manager one (which the
// agent's Skills tab reads even though the skill routes themselves live
// elsewhere). The list envelope around it is declared inline in that contract,
// with no schema of its own to alias, so it stays written out below.
import type { components } from "@/lib/api/generated/agent-registry";
import type { components as SkillManager } from "@/lib/api/generated/skill-manager";

type Schemas = components["schemas"];

export type McpEntryOut = Schemas["McpEntry"];

export type McpEntriesResponse = Schemas["McpEntriesOut"];

export type AdoptMcpEntryBody = Schemas["McpEntryAdopt"];

/** What adopting an MCP entry created: `uid`, `kind`, `name`. The uid is where
 *  the caller navigates, the name is what it tells the user the thing ended up
 *  being called — after a `new_name` override those are not the same answer,
 *  which is why both travel. */
export type AdoptedResource = Schemas["AdoptedResource"];

/** What adopting an unmanaged skill folder created: the new skill's uid and the
 *  label it was adopted under. Same two answers, same reason. */
export type SkillRefOut = SkillManager["schemas"]["SkillRefOut"];

/** `version` … `mcp_servers`: best-effort detail read from the plugin's
 * install dir (Claude only today; null / empty otherwise). */
export type PluginOut = Schemas["Plugin"];

/** `can_uninstall`: whether in-app uninstall is available for this agent now
 * (capability +, for CLI-strategy agents like Claude, the agent's CLI being on
 * PATH). */
export type PluginsResponse = Schemas["PluginsOut"];

/** `location` is the scan location the entry was found in — `skills` is
 * `<config_dir>/skills`, `agents_dir` the agent product's secondary standard
 * location. Taken from the contract, so it is the two names and not `string`. */
export type UnmanagedSkillOut = SkillManager["schemas"]["UnmanagedSkillOut"];

export interface UnmanagedSkillsResponse {
  items: UnmanagedSkillOut[];
}
