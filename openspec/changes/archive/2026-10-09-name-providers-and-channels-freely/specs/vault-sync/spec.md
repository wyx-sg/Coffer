## MODIFIED Requirements

### Requirement: Converge resources as their own files
`mcp_server`, `skill`, `provider` and `knowledge` resources MUST
converge as their files, `vault/resources/<kind>/<name>.json` (`<uid>.json` for a provider) — the file is the
resource, not a serialization of a row kept elsewhere ([vault-storage](../vault-storage/spec.md)
"Identify a resource by the uid inside its file"). A resource file is identity,
name, description and config — what the resource *is*; what it reaches is not
in it (see "Keep reach machine-local"). Agents and channels are machine-local
and never converge: a channel's file, like an agent's, is under `local/`
([channels](../channels/spec.md) "Keep each channel on the machine that holds it").

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** its file is read from the vault
- **THEN** the file holds its uid, kind, name, description and config
- **AND** it holds no `enabled` flag and no `scope`, and the vault's history never carries them
