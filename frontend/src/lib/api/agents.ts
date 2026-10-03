// frontend/src/lib/api/agents.ts — request helpers for /api/v1/agents/*
//
// Every route here is addressed by the agent's `uid` (ADR
// identity-is-the-uid-inside-the-file). An agent is one per type per machine
// and its name is the type's fixed name (`claude-code` / `codex`); what a
// heading and a table row show is `AgentOut.display_name`.
//
// Wire types are the agent-registry contract's generated schemas
// (`openspec/specs/agent-registry/contracts/api.openapi.yaml` → `generated/agent-registry.ts`),
// under the names the hooks and pages import. Transport is the typed client
// (.agents/frontend.md §4).
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { components } from "@/lib/api/generated/agent-registry";

import type { AdoptMcpEntryBody, AdoptSkillReach, UnmanagedSkillOut } from "./agents-workspace";

type Schemas = components["schemas"];

/** Which scan location an unmanaged skill lives in (`skills` | `agents_dir`).
 *  Callers hold it as the URL's string, so the daemon is what rejects an unknown one (422). */
const loc = (location: string) => location as UnmanagedSkillOut["location"];

// Keep AgentType in sync with the backend domain (`domain/agent/types.py`).
export type AgentType = Schemas["AgentType"];

export type ConfigFileInfo = Schemas["ConfigFileInfoOut"];

/** Body of a config-file save. `expected_fingerprint` makes the write
 *  conditional: the daemon refuses it with 409 CONFIG_FILE_STALE when the file
 *  changed on disk since the read that produced the fingerprint. */
export type ConfigFileWrite = Schemas["ConfigFileWrite"];

/** An agent's Coffer connection: every part Coffer writes into the agent
 *  that applies now (`mcp` always, `memory_hook` while memory is on), and a
 *  state derived from them — `partial` is "needs repair". */
export type CofferConnection = Schemas["CofferConnectionOut"];

export type AgentOut = Schemas["AgentOut"];

export type AgentCreate = Schemas["AgentCreate"];

export type AgentPatch = Schemas["AgentPatch"];

/** One supported agent type on this machine: its fixed name, detection state,
 *  directories, and — when registered — its uid. `addable` says whether
 *  registering it now would succeed. */
export type AgentTypeOut = Schemas["AgentTypeOut"];

/** Every hook in the agent's native config, plus Coffer's own hook's health. */
export type AgentHooksOut = Schemas["AgentHooksOut"];
export type NativeHook = Schemas["NativeHookOut"];
export type CofferHook = Schemas["CofferHookOut"];

export const agentsApi = {
  list: () => unwrap(getApiClient().GET("/agents")),
  register: (body: AgentCreate) => unwrap(getApiClient().POST("/agents", { body })),
  get: (uid: string) => unwrap(getApiClient().GET("/agents/{uid}", { params: { path: { uid } } })),
  patch: (uid: string, body: AgentPatch) =>
    unwrap(getApiClient().PATCH("/agents/{uid}", { params: { path: { uid } }, body })),
  // One row per supported type, registered or not.
  types: () => unwrap(getApiClient().GET("/agents/types")),

  // Config files are read AND written in-app. A write carries the fingerprint
  // from the read that seeded the editor, so a file changed underneath the
  // editor is refused (409) rather than overwritten.
  listConfigFiles: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/config-files", { params: { path: { uid } } })),
  readConfigFile: (uid: string, key: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/config-files/{key}", { params: { path: { uid, key } } }),
    ),
  writeConfigFile: (uid: string, key: string, body: ConfigFileWrite) =>
    unwrap(
      getApiClient().PUT("/agents/{uid}/config-files/{key}", {
        params: { path: { uid, key } },
        body,
      }),
    ),

  // Read-only: every hook the agent's own files and enabled plugins declare.
  hooks: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/hooks", { params: { path: { uid } } })),

  connection: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/coffer-connection", { params: { path: { uid } } })),
  connect: (uid: string) =>
    unwrap(getApiClient().POST("/agents/{uid}/coffer-connection", { params: { path: { uid } } })),
  disconnect: (uid: string) =>
    unwrap(getApiClient().DELETE("/agents/{uid}/coffer-connection", { params: { path: { uid } } })),

  // MCP entries (spec agent-registry "List the MCP entries in the agent's own config files")
  mcpEntries: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/mcp-entries", { params: { path: { uid } } })),
  // One entry in full, read-only. `source` is sent whenever known — it is what
  // tells two same-named entries (claude_code's two files) apart.
  mcpEntry: (uid: string, entry: string, source?: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/mcp-entries/{entry}", {
        params: { path: { uid, entry }, query: { source: source || undefined } },
      }),
    ),
  // Deletes the entry from the agent's own config file (a .bak is written by
  // the daemon). `source` names which config file the entry came from — an
  // entry name can repeat across sources.
  removeMcpEntry: (uid: string, entry: string, source?: string) =>
    unwrapVoid(
      getApiClient().DELETE("/agents/{uid}/mcp-entries/{entry}", {
        params: { path: { uid, entry }, query: { source: source || undefined } },
      }),
    ),
  adoptMcpEntry: (uid: string, entry: string, body: AdoptMcpEntryBody) =>
    unwrap(
      getApiClient().POST("/agents/{uid}/mcp-entries/{entry}/adopt", {
        params: { path: { uid, entry } },
        body,
      }),
    ),

  // Plugins (spec agent-registry "List an agent's installed plugins without writing anything"). Enable/disable
  // writes the agent's documented config surface; uninstall drops the entry
  // (Codex) or delegates to the agent's own CLI (Claude Code).
  plugins: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/plugins", { params: { path: { uid } } })),
  plugin: (uid: string, id: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/plugins/{plugin_id}", {
        params: { path: { uid, plugin_id: id } },
      }),
    ),
  togglePlugin: (uid: string, id: string, enabled: boolean) =>
    unwrapVoid(
      getApiClient().PATCH("/agents/{uid}/plugins/{plugin_id}", {
        params: { path: { uid, plugin_id: id } },
        body: { enabled },
      }),
    ),
  uninstallPlugin: (uid: string, id: string) =>
    unwrapVoid(
      getApiClient().DELETE("/agents/{uid}/plugins/{plugin_id}", {
        params: { path: { uid, plugin_id: id } },
      }),
    ),

  // Config-file child (per-file inside a directory-backed config key). The
  // relpath is a POSIX path; the client escapes its separators into one path
  // segment and the daemon's `:path` route reads it back as the path.
  readConfigChild: (uid: string, key: string, relpath: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/config-files/{key}/files/{relpath}", {
        params: { path: { uid, key, relpath } },
      }),
    ),
  writeConfigChild: (uid: string, key: string, relpath: string, body: ConfigFileWrite) =>
    unwrap(
      getApiClient().PUT("/agents/{uid}/config-files/{key}/files/{relpath}", {
        params: { path: { uid, key, relpath } },
        body,
      }),
    ),
  // Deletes one file inside a directory entry (the daemon keeps a .bak).
  deleteConfigChild: (uid: string, key: string, relpath: string) =>
    unwrapVoid(
      getApiClient().DELETE("/agents/{uid}/config-files/{key}/files/{relpath}", {
        params: { path: { uid, key, relpath } },
      }),
    ),

  // Unmanaged skills (spec skill-manager "List unmanaged skills in an agent's skill locations")
  unmanagedSkills: (uid: string) =>
    unwrap(getApiClient().GET("/agents/{uid}/unmanaged-skills", { params: { path: { uid } } })),
  adoptUnmanagedSkill: (
    uid: string,
    skill: string,
    location: string,
    options: { name?: string | null; reach?: AdoptSkillReach | null } = {},
  ) =>
    unwrap(
      getApiClient().POST("/agents/{uid}/unmanaged-skills/{skill}/adopt", {
        params: { path: { uid, skill } },
        body: { location: loc(location), name: options.name, reach: options.reach },
      }),
    ),
  // Read-only preview of one unmanaged folder (spec skill-manager "Preview an
  // unmanaged skill read-only") — the same tree/content shapes as a managed
  // skill's Files tab, addressed by folder name + scan location.
  unmanagedSkill: (uid: string, skill: string, location: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/unmanaged-skills/{skill}", {
        params: { path: { uid, skill }, query: { location: loc(location) } },
      }),
    ),
  unmanagedSkillFiles: (uid: string, skill: string, location: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/unmanaged-skills/{skill}/files", {
        params: { path: { uid, skill }, query: { location: loc(location) } },
      }),
    ),
  unmanagedSkillFileContent: (uid: string, skill: string, location: string, path: string) =>
    unwrap(
      getApiClient().GET("/agents/{uid}/unmanaged-skills/{skill}/files/content", {
        params: { path: { uid, skill }, query: { location: loc(location), path } },
      }),
    ),
  deleteUnmanagedSkill: (uid: string, skill: string, location: string) =>
    unwrapVoid(
      getApiClient().DELETE("/agents/{uid}/unmanaged-skills/{skill}", {
        params: { path: { uid, skill }, query: { location: loc(location) } },
      }),
    ),
};
