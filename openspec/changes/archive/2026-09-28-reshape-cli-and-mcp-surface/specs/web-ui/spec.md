## ADDED Requirements

### Requirement: Show and edit a title on MCP server and skill pages
The MCP server and skill list and detail pages MUST show a resource's title in place of its name
wherever the resource is named — the list row, the detail page header and the delete
confirmation — and MUST show the name when no title is set
([resource-framework](../resource-framework/spec.md) "Carry an optional editable title on every resource").
Where a title is shown, the name MUST stay visible beside it as secondary text, because the name
is what an agent sees. Each detail page MUST let the user set, change and clear the title, and
MUST show the name as fixed, with no control that edits it and a note saying the name cannot
change after registration. The list's search box MUST match both the title and the name.

#### Scenario: a titled server is listed and headed by its title
- **GIVEN** a registered MCP server with no title
- **WHEN** the user sets its title on the detail page, and then opens the MCP servers list and searches for its name
- **THEN** the detail header and the list row show the title, each with the name beside it as secondary text
- **AND** the search finds the row by its name, and the detail page offers no control that edits the name

#### Scenario: clearing a skill's title shows its name again
- **GIVEN** a skill whose title is set
- **WHEN** the user clears the title on the skill's detail page
- **THEN** the detail header and the skills list show the skill's name
- **AND** the page still marks the name as fixed

### Requirement: Read each Activity tab from its record owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose) — the
Changes tab `GET /api/v1/audit`, the MCP calls tab `GET /api/v1/mcp/invocations`
and the Daemon tab `GET /api/v1/daemon/logs`. An agent or a script that asks
"what happened" reads the same three records from the command line (see "Keep
the command-line record readers").

#### Scenario: each activity tab reads its owner's route
- **GIVEN** a running daemon that has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens each of the three Activity tabs in turn
- **THEN** the Changes tab requests only `GET /api/v1/audit`, the MCP calls tab only `GET /api/v1/mcp/invocations`, and the Daemon tab only `GET /api/v1/daemon/logs`
- **AND** no tab requests a route of the Activity page's own

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

The review step MUST show each server's name, taken from its key in the pasted block, as the
name the server will keep: it cannot be changed after registration
([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources"). A name longer than
24 characters MUST be flagged in the review, before submit, with a message naming the limit, and
the dialog MUST NOT send that server's registration until the name is shortened in the pasted
block.

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

#### Scenario: the import review shows each server's fixed name
- **GIVEN** the user pastes an `mcpServers` block holding one server keyed with a 12-character name and one keyed with a 30-character name
- **WHEN** the review step is shown
- **THEN** each server's name is shown with a note that it cannot be changed after registration, and the 30-character name is flagged with the 24-character limit
- **AND** no request is sent to `/api/v1/resources` for the flagged server while its name is over the limit

### Requirement: Keep the command-line record readers
Each of the three records the Activity page shows MUST also be readable from the
command line, over the same route the page reads: `coffer log audit` reads the
audit log (`GET /api/v1/audit`), `coffer log mcp` reads the invocation log, and
`coffer log daemon` reads the daemon log (`GET /api/v1/daemon/logs`). Without
`--server`, `coffer log mcp` reads the same cross-server log the MCP calls tab
renders (`GET /api/v1/mcp/invocations`), Coffer's own built-in calls (`coffer`)
and deleted servers' rows (`deleted:<name>`) included; with `--server <name>`, it
reads that server's log. Each reader takes `--since`, `--limit` and `--json`,
plus the filter its record affords: `--status` for invocations, and `--errors`
for the daemon log.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry, MCP invocations on
  two servers, on Coffer's own built-in tools and on a deleted server, and a daemon
  log record
- **WHEN** a script runs `coffer log audit`, `coffer log mcp --server <server>`,
  `coffer log mcp` with no server and `coffer log daemon`
- **THEN** each exits successfully and prints that record's entries, the per-server
  reader only that server's calls and the reader with no server every row, each
  naming its server
- **AND** with `--json` each prints one parseable document and no human-readable framing

## REMOVED Requirements

### Requirement: Read each Activity record from its owner's route
**Reason**: The requirement assumed the built-in `coffer__diagnose` tool, which is removed; an agent reads the same records with `coffer log` and the daemon log file that `coffer path logs` names.
**Migration**: The Activity page's routing rule moves unchanged to "Read each Activity tab from its record owner's route", and an agent that called `coffer__diagnose` runs `coffer log audit` and `coffer log daemon --errors --since <window>` instead (see "Keep the command-line record readers").
