// frontend/src/lib/api/agents-workspace.ts — wire types for the agent workspace
// surfaces (MCP entries, plugins, unmanaged skills). Split out of agents.ts for
// the file-size budget; importers take these types from here.
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

export type McpEntryOut = Schemas["McpEntryOut"];

/** One entry in full — the listing's fields plus the config file's `path`,
 *  `cwd` and every other key (`extra`, secret-looking values masked by the
 *  daemon: `value: null, masked: true`). */
export type McpEntryDetailOut = Schemas["McpEntryDetailOut"];

export type McpEntriesResponse = Schemas["McpEntriesOut"];

export type AdoptMcpEntryBody = Schemas["McpEntryAdopt"];

/** What adopting an MCP entry created: `uid`, `kind`, `name`. The uid is where
 *  the caller navigates, the name is what it tells the user the thing ended up
 *  being called — after a `new_name` override those are not the same answer,
 *  which is why both travel. */
export type AdoptedResource = Schemas["AdoptedOut"];

/** `version` … `mcp_servers`: best-effort detail read from the plugin's
 * install dir (Claude only today; null / empty otherwise). */
export type PluginOut = Schemas["PluginOut"];

/** `can_uninstall`: whether in-app uninstall is available for this agent now
 * (capability +, for CLI-strategy agents like Claude, the agent's CLI being on
 * PATH). */
export type PluginsResponse = Schemas["PluginsOut"];

/** One plugin's detail page: its listing row (`plugin`), marketplace source,
 * the directory its package was read from, `can_uninstall`, and the skills /
 * commands / subagents (with descriptions), hook events and MCP servers it
 * contributes. */
export type PluginDetailOut = Schemas["PluginDetailOut"];

/** `location` is the scan location the entry was found in — `skills` is
 * `<config_dir>/skills`, `agents_dir` the agent product's secondary standard
 * location. Taken from the contract, so it is the two names and not `string`. */
export type UnmanagedSkillOut = SkillManager["schemas"]["UnmanagedSkillOut"];

/** One unmanaged skill for its read-only detail page: the list entry plus the
 *  SKILL.md `description` (null when the folder does not validate). */
export type UnmanagedSkillDetailOut = SkillManager["schemas"]["UnmanagedSkillDetailOut"];
