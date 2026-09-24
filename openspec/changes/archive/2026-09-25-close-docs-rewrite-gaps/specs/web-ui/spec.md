## MODIFIED Requirements

### Requirement: Import MCP servers from pasted JSON
"Add MCP server" MUST be a modal that takes the standard `mcpServers` JSON
block — the same block every MCP server's README provides — one server or many
at once, with a review step where the user confirms which values are secrets.
The review covers every server's `env` values and, for an HTTP server, the
values of its `headers` object too, read with the same secret detection as
`env` rather than ignored (a header and an `env` entry of the same name are one
header, the `headers` value winning). Secrets MUST
be lifted into the encrypted credential store with only their refs kept in the
resource config, and the server MUST be registered before its secrets are
written, so a failed registration leaves no orphan credential entry.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the "Add MCP server" dialog from the resources list
- **WHEN** they paste the standard `mcpServers` JSON and confirm the review step
- **THEN** the app posts each server to `/api/v1/resources`, then writes any secret env values to `/api/v1/credentials` (register-first ordering avoids orphan credential entries when registration fails)
- **AND** on success the dialog closes and (for a single server) the app navigates to the server's detail page `/mcp-servers/<uid>` showing the Overview tab
- **AND** the new server appears on the resources list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the JSON-import dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server card appears in the resources list

#### Scenario: a pasted HTTP server's headers are reviewed for secrets
- **GIVEN** the user pastes an `mcpServers` block holding an HTTP server with a `headers` object that carries an `Authorization` value
- **WHEN** the review step is shown and confirmed
- **THEN** the header is offered as a secret, its value is written to the credential store, and the registered server keeps only its ref (`credential_refs`), never the value in `headers`
