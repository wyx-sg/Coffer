## ADDED Requirements

### Requirement: Add MCP servers by pasting them into one box
The MCP servers page MUST carry one **Add server** action, and no separate
paste-JSON action. It opens a modal whose first step is one paste box that
recognises what was pasted, so the user can paste whatever an MCP server's
README gives them:

- an `mcpServers` JSON block, or a single server object, holding one server or
  many;
- Codex TOML `[mcp_servers.<name>]` tables, one or many;
- a command line, including `claude mcp add …` and `codex mcp add …`, which
  becomes a stdio server — its name, environment (`-e` / `--env`) and command
  taken from the command, a plain command's name suggested from its package;
- a URL, which becomes a Streamable HTTP server, its name suggested from the
  host.

One recognised server MUST open the manual form prefilled with it; several MUST
open the review step. The dialog MUST NOT offer importing the direct MCP
entries in the agents' own config files: that is done on each agent's MCP
servers tab ([agent-registry](../agent-registry/spec.md) "Adopt a direct MCP entry into Coffer"). While no
server is registered, the page's welcome MAY list those entries per agent, each
row opening that agent's MCP servers tab. The dialog adds MCP servers only: it offers no
custom tool (an HTTP API imported from an OpenAPI document or defined by hand),
which is added on the Custom tools page (see "Manage custom tool groups on their
own page").

The review step covers every server's environment values and, for an HTTP
server, the values of its `headers` too, read with the same secret detection as
the environment rather than ignored (a header and an environment entry of the
same name are one header, the `headers` value winning). The user confirms which
values are secrets; secrets MUST be lifted into the encrypted secret store
with only their refs kept in the resource config, and each server MUST be
registered before its secrets are written, so a failed registration leaves no
orphan secret entry. The user also chooses the servers' reach there.

The review step MUST show each server's name as the name it will keep: it
cannot be changed after registration
([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources"). Each
name is taken from its key, table or command, normalised to the pattern
mcp-gateway allows — lower case, other characters turned into hyphens — and can
be corrected in the review before it is added. A name longer than 24
characters MUST be flagged, before submit, with a message naming the limit, and
the dialog MUST NOT send that server's registration until the name is shortened.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the Add server dialog from the MCP servers page
- **WHEN** they paste the standard `mcpServers` JSON holding one server and add it from the prefilled form
- **THEN** the app posts the server to `/api/v1/resources`, then writes any secret env values to `/api/v1/secrets` (register-first ordering avoids orphan secret entries when registration fails)
- **AND** on success the dialog closes and the app navigates to the server's detail page `/mcp-servers/<name>` showing the Overview tab
- **AND** the new server appears on the MCP servers list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the Add server dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server appears in the MCP servers list

#### Scenario: a pasted HTTP server's headers are reviewed for secrets
- **GIVEN** the user pastes an `mcpServers` block holding an HTTP server with a `headers` object that carries an `Authorization` value
- **WHEN** the review step is shown and confirmed
- **THEN** the header is offered as a secret, its value is written to the secret store, and the registered server keeps only its ref (`secret_refs`), never the value in `headers`

#### Scenario: the import review shows each server's fixed name
- **GIVEN** the user pastes an `mcpServers` block holding one server keyed `My Server` and one keyed with a 30-character name
- **WHEN** the review step is shown
- **THEN** each server's name is shown with a note that it cannot be changed after registration, the first normalised to `my-server`, and the 30-character name is flagged with the 24-character limit
- **AND** no request is sent to `/api/v1/resources` for the flagged server until its name is shortened in the review

#### Scenario: pasting JSON with three servers opens the review
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes an `mcpServers` block holding three servers
- **THEN** the dialog recognises three servers and opens the review step listing all three with their detected secrets and a reach choice
- **AND** confirming registers the three servers, each before its secrets are written

#### Scenario: pasting a command line prefills a stdio server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github`
- **THEN** the manual form opens prefilled as a stdio server named `github` with command `npx`, arguments `-y @modelcontextprotocol/server-github` and `GITHUB_TOKEN` offered as a secret

#### Scenario: pasting a URL prefills a Streamable HTTP server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `https://mcp.example.com/mcp`
- **THEN** the manual form opens prefilled as a Streamable HTTP server with that URL and a name suggested from the host

#### Scenario: pasting Codex TOML reads its server tables
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes a `[mcp_servers.docs]` table with a command, arguments and an `env` table
- **THEN** the manual form opens prefilled as a stdio server named `docs` with that command, arguments and environment, the secret-looking values offered as secrets

#### Scenario: the add dialog offers no import from agents
- **GIVEN** the MCP servers page, and an agent whose own config file holds a direct MCP entry
- **WHEN** it renders and the user opens Add server
- **THEN** the page carries one Add server action and no separate paste-JSON action, and the dialog carries no Import from agents link
- **AND** the dialog offers no custom tool, neither an OpenAPI import nor a hand-made HTTP request

## REMOVED Requirements

### Requirement: Review an import from the agents before it is applied
**Reason**: Importing the agents' own MCP entries lives on each agent's MCP servers tab only; the Add server dialog no longer offers a batch import.
**Migration**: Adopt each entry from the agent's MCP servers tab ([agent-registry](../agent-registry/spec.md) "Adopt a direct MCP entry into Coffer"); `coffer agent mcp-import apply` still imports several at once.

### Requirement: Add MCP servers from one paste box
**Reason**: Restated as "Add MCP servers by pasting them into one box", which drops the dialog's Import from agents link (a requirement's scenarios cannot be dropped by a MODIFIED delta).
**Migration**: "Add MCP servers by pasting them into one box"; its scenarios keep their names except "the add dialog links to importing from agents", now "the add dialog offers no import from agents".
