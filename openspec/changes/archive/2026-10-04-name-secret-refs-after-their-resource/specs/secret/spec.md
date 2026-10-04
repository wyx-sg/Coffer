## ADDED Requirements

### Requirement: Name a resource's secret after the resource and its slot
A secret a resource owns — the resource is its only citer, in one slot — MUST be
named `<kind>/<name>/<slot>`: the resource's kind, its name with every character
outside `[A-Za-z0-9_.-]` replaced by `-`, and the slot it fills (an MCP server's
env var or header name; a channel's `bot-token`, `app-secret`,
`signing-secret` or `tunnel-token`; a provider's `key`). Every place Coffer
mints a ref for a resource — the MCP server and channel dialogs, provider
creation, the plaintext import — MUST mint that name, with `-2`, `-3`, … on the
name segment when it is already taken by another citer's ref.

Renaming a channel or a provider MUST move every secret it owns to the new
name. At daemon start every owned secret not yet named this way MUST be moved
to its name. A move writes the value under the new ref and reads it back,
changes the citing config through the resource service, carries this machine's
binding, creation time and last-used stamp to the new ref, and deletes the old
one; a failure before the config changes leaves the old ref cited and removes
the new one. A secret cited by more than one resource or slot, and every
standalone `secret/<name>`, MUST keep its ref. Each move MUST be audited as
`secret_renamed` naming both refs, never the value.

#### Scenario: a new MCP server's secret is named after it
- **GIVEN** an MCP server `confluence` registered with a pasted `CONFLUENCE_PERSONAL_TOKEN`
- **WHEN** its config is read
- **THEN** it cites `mcp_server/confluence/CONFLUENCE_PERSONAL_TOKEN`, which holds the value

#### Scenario: renaming a provider moves its key
- **GIVEN** a provider `agnes` whose key is `provider/agnes/key`
- **WHEN** it is renamed `agnes-hub`
- **THEN** it cites `provider/agnes-hub/key`, which holds the same value, `provider/agnes/key` no longer exists, and the provider still resolves its key with no approval waiting

#### Scenario: start-up names an owned secret and leaves a shared one
- **GIVEN** a server citing a ref `mcp_server/<uuid hex>/JIRA_TOKEN` nothing else cites, a provider citing `agnes-apihub`, two servers citing the same `team.TOKEN`, and a standalone `secret/github`
- **WHEN** the daemon starts
- **THEN** the server cites `mcp_server/<its name>/JIRA_TOKEN` and the provider `provider/<its name>/key`, each holding its old value, with the old refs gone and one `secret_renamed` entry each
- **AND** `team.TOKEN` and `secret/github` are unchanged, and a second start moves nothing

## MODIFIED Requirements

### Requirement: Keep secret values out of secret audit events
The events `secret_set`, `secret_revealed`, `secret_deleted`,
`master_key_relocated`, `master_key_exported`, `secret_resolved`, `secret_imported`,
`secret_renamed` and the
`secret_approval_*` events MUST carry the ref, the name or the destination only. An audit payload
MUST NOT carry a secret value, and a new secret event that does MUST NOT be added.

#### Scenario: secret audit events carry the ref only
- **GIVEN** a running daemon
- **WHEN** a secret is stored and deleted through the API
- **THEN** the `secret_set` and `secret_deleted` entries each carry the ref
- **AND** none of those entries contains the secret value anywhere in its payload
