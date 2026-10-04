## MODIFIED Requirements

### Requirement: Validate config-file content before saving it
The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor and the REST API — one endpoint serving both. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown` files accept any content.

#### Scenario: reject malformed config-file content
- **GIVEN** a registered agent whose `settings.json` (a `json` file) exists
- **WHEN** the user writes malformed content (e.g. invalid JSON) to that key through the in-app editor or the REST API
- **THEN** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no backup, and records no write audit entry

### Requirement: Write config files atomically with a backup and an audit entry
Writes MUST be atomic (temp file + rename) and MUST copy the prior content, before the replace, to a timestamped backup under `~/.coffer/config-backups/` (Coffer's own folder: machine-local, outside the vault, and never beside the agent's file) so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (see "Back up and audit Coffer MCP install and uninstall") reuse the same atomic-write + backup machinery. Backups are named by their UTC time and cleaned by the `config_backups` retention policy ([resource-framework](../resource-framework/spec.md) "Retain config backups on an adjustable policy"), which always keeps the newest backup of each file.

#### Scenario: save a config file with valid content
- **GIVEN** a registered agent whose `settings.json` exists
- **WHEN** the user writes new, well-formed content to that config-file key through the in-app editor or the REST API
- **THEN** Coffer validates the content against the file's format, writes it atomically while copying the prior version to a backup under `~/.coffer/config-backups/` (nothing is written next to the file), records an `agent_config_file_written` audit entry, and the new content reads back on the next read

#### Scenario: a config write leaves its backup in Coffer's folder and nothing beside the file
- **GIVEN** `~/.claude/settings.json` holds content, and an older write already left a backup of it
- **WHEN** Coffer writes new content to that file twice
- **THEN** each write copied the prior content to its own timestamped file under `~/.coffer/config-backups/`, in a folder named for that one config file, and the newest backup holds the content the last write replaced
- **AND** no `.bak` file, backup or temporary file is left in the agent's own directory, and nothing under `~/.coffer/vault` was written

### Requirement: Back up and audit Coffer MCP install and uninstall
Install and uninstall MUST reuse the atomic-write + backup machinery of "Write config files atomically with a backup and an audit entry" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up under `~/.coffer/config-backups/`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

### Requirement: Remove a direct MCP entry from its source file
Users MUST be able to remove a direct MCP entry — from the agent's page or the REST route (`DELETE /api/v1/agents/{uid}/mcp-entries/{entry}`). Removal edits only the entry's source file, reuses the atomic-write + backup machinery of "Write config files atomically with a backup and an audit entry", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a backup of the prior content under `~/.coffer/config-backups/`, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: remove a direct MCP entry over REST and refuse the coffer entry
- **GIVEN** a registered agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user sends `DELETE /api/v1/agents/claude-code/mcp-entries/github`
- **THEN** the entry is gone from its source file, the newest backup under `~/.coffer/config-backups/` holds the prior content, and an `agent_mcp_entry_removed` audit entry is recorded
- **AND** `DELETE /api/v1/agents/claude-code/mcp-entries/coffer` is refused and leaves the file unchanged

### Requirement: Adopt a direct MCP entry into Coffer
Users MUST be able to adopt a direct MCP entry into Coffer, so that it is served to every agent through the gateway instead of benefiting one agent alone — from the agent's page or the REST route (`POST /api/v1/agents/{uid}/mcp-entries/{entry}/adopt`), whose `new_name` registers the server under a different name than the entry's. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per "Remove a direct MCP entry from its source file" — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical, reporting the failure with a specific error code; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.

#### Scenario: adopt a direct MCP entry into Coffer
- **GIVEN** a registered agent with a direct stdio MCP entry whose name collides with no existing resource
- **WHEN** the user adopts the entry
- **THEN** Coffer first registers an equivalent `mcp_server` resource (schema-validated, audited), verifies it reads back, then removes the direct entry from the agent's config (atomic + backup), records an `agent_mcp_entry_adopted` audit entry, and the upstream is now served to all agents through the gateway

#### Scenario: reject adoption on resource name conflict
- **GIVEN** an `mcp_server` resource already exists with the same name as a direct entry
- **WHEN** the user adopts that entry without renaming
- **THEN** the request is rejected with `conflict` (409) carrying a suggested alternative name, no resource is created, and the agent's config is untouched

#### Scenario: adoption failure leaves agent config untouched
- **GIVEN** an adoption attempt that fails after resource registration (e.g. the config-file write is rejected as stale)
- **WHEN** the operation aborts
- **THEN** the created resource is rolled back, the agent's config file is byte-identical to before the attempt, and the failure is reported with a specific error code

#### Scenario: adopt a direct MCP entry under a new name
- **GIVEN** an `mcp_server` resource named `github` and an agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user adopts the entry with `POST /api/v1/agents/claude-code/mcp-entries/github/adopt` carrying `new_name` `github-work`
- **THEN** an `mcp_server` resource named `github-work` is registered and the direct entry is gone from the agent's config
- **AND** an `agent_mcp_entry_adopted` audit entry is recorded

### Requirement: Read, write and delete files inside a directory entry
Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor, . Write (create-on-write) and delete of individual files are available through the in-app editor and the REST API (`PUT` and `DELETE /api/v1/agents/{uid}/config-files/{key}/files/{relpath}`). Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension — a containment violation is `not_found` (404) and a disallowed extension `unprocessable_entity` (422). Writes reuse the machinery of "Write config files atomically with a backup and an audit entry"; deletion preserves the prior content as a backup under `~/.coffer/config-backups/`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.

#### Scenario: create a file inside a directory entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user writes content to a new `.md` file path inside the entry through the in-app editor or the REST API
- **THEN** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it

#### Scenario: delete a file inside a directory entry
- **GIVEN** a directory entry containing a file
- **WHEN** the user deletes that file through the REST API
- **THEN** the file is removed with its prior content preserved as a backup under `~/.coffer/config-backups/`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it

#### Scenario: reject directory file paths outside the entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension
- **THEN** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension

### Requirement: Reject stale config-file writes by fingerprint
Config-file reads (single files and directory children) MUST return a content fingerprint. A write MAY carry that fingerprint back; a write that carries one MUST be rejected with `conflict` (409, `CONFIG_FILE_STALE`) when the on-disk content changed since the read, leaving the file untouched. A write that carries none is applied as sent, for scripted REST use. The in-app editor MUST always send the fingerprint of the read it started from, because it holds the file open for as long as the user edits — exactly the window another writer lands in. The agent's own process may rewrite a file between Coffer's read and write; the user then re-reads and retries, and the backup of every Coffer write keeps the prior content recoverable in the reverse race.

#### Scenario: reject stale config-file writes
- **GIVEN** a config file (or directory child) read by the user, then modified on disk by another process
- **WHEN** the user writes back content carrying the fingerprint from the earlier read
- **THEN** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write

#### Scenario: write a config file over REST
- **GIVEN** a registered agent with an existing `json` config file under the allowlisted key `<key>`, and well-formed JSON content to write
- **WHEN** the user writes that content with `PUT /api/v1/agents/{uid}/config-files/<key>`
- **THEN** the config file holds the written content, the newest backup under `~/.coffer/config-backups/` holds the prior content, and an `agent_config_file_written` audit entry is recorded
- **AND** the same request with malformed JSON is refused with `unprocessable_entity` (422) and leaves the config file unchanged

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration for that agent's type:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action", for every agent type;
- `memory_hook` — the memory delivery hook of [memory](../memory/spec.md) "Install delivery hooks explicitly and removably", for every agent type with a hook adapter.

The gateway entry MUST be installed first, so that a connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a backup and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent with neither the gateway entry nor the memory hook
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry and its `settings.json` carries Coffer's marked hook entry
- **AND** one `agent_mcp_installed` and one `memory_delivery_installed` audit entry name the user as actor, and the connection reports `connected` with both parts installed

