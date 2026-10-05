## MODIFIED Requirements

### Requirement: Never expose Codex's credential file
`<config_dir>/auth.json` MUST never enter the allowlist, any config-file listing, or any facet's parse. It is a credential file: no config-file route lists or reads it — a preview is addressed only by an allowlisted key ([agent-registry](../spec.md) "Preview an agent's config file read-only") — and neither the MCP-entry nor the plugin parser opens it.

#### Scenario: refuse to read auth.json
- **GIVEN** a registered `codex` agent whose config directory holds an `auth.json`
- **WHEN** the user lists the agent's config files and then requests `auth.json`'s preview under the config-file routes
- **THEN** the listing does not include it
- **AND** the request is answered `404` with no filesystem read
