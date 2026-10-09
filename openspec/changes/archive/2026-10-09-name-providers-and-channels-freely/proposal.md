## Why

A provider and a channel carried two labels: a slug `name` held to `^[a-zA-Z0-9_.-]+$` and an
optional free-text `title` that every surface showed in its place. The slug exists for the kinds
whose name is quoted outside Coffer (an MCP server's name is in every tool name an agent calls, a
skill's is the directory an agent loads), and those kinds already carry no title. A provider and a
channel are named only on Coffer's own surfaces, so for them the slug had no reader and the title
existed only to get around it: surfaces had to choose between two labels, the Add channel dialog
derived a slug nobody chose (and nothing usable from Chinese text), and a rename changed one label
and not the other. The reasoning, with the products compared, is the ADR
[A Provider's and a Channel's Name Is Free Text, and Their Files Are Named by uid](../../../docs/decisions/provider-and-channel-names-are-free-text.md).

## What Changes

- **BREAKING (wire):** no resource kind carries a `title` any more. The key is gone from every REST
  body and response, from the resource file in the vault and from the `coffer` command help.
- `provider` and `channel` names are free text: trimmed, NFC-normalised, 1 to 80 characters, no
  control character, not starting with `-`; refused as a validation error otherwise. Unique within
  the kind ignoring case; a case-only rename of a resource's own name is allowed. Renamed through the
  ordinary `PATCH /api/v1/resources/{uid}`.
- A provider's and a channel's file is `resources/<kind>/<uid>.json` and a rename never moves it.
  Every other kind keeps its slug name and its name-derived file.
- The vault validator applies the same per-kind name rule, and its name-taken check ignores case for
  these two kinds.
- A one-time migration on start rewrites every provider and channel file with the old shape: the
  title becomes the name (`" (2)"`, `" (3)"`… on a clash ignoring case), the `title` key is dropped
  and the file moves to `<uid>.json`. It is a pure function of the files, so two machines write the
  same commit.
- Channels: the Add dialog registers the typed display name as the channel's name; the Settings tab
  renames it. The turn's origin block reads `channel: "<name>" (id: <uid>)` and
  `coffer__channel_read_thread` takes the channel's id.
- The vault layout version is not raised; a machine on the previous build stops its sync round on a
  migrated file until it is updated.

## Capabilities

### Modified Capabilities

- `resource-framework`: the title requirement is renamed "Name a provider or a channel with free
  text" and now states the name rule, case-insensitive uniqueness, uid file names and the migration;
  the uid-surface, rename, audit-CLI, hint and registration requirements drop the title.
- `channels`: "Name a channel by any display name", the Channels page, the typed-setting commit, the
  message origin and the thread-reading tool.
- `provider-switching`: renaming a connection to free text; the connection file is `<uid>.json`.
- `vault-storage`, `vault-sync`: the resource document has no title; the file path for providers.
- `mcp-gateway`, `skill-manager`, `agent-registry`, `web-ui`: a kind with no title no longer cites
  the title requirement; the scenarios that submitted a title are removed.

## Impact

Backend (`domain/resource.py`, the resource service and store, the vault validator, the migration in
`infrastructure/vault/free_name_migration.py`, the channel service and thread tool), the frontend
(no title in its place of the name), the OpenAPI contracts, `docs-site/` and the ADR.
