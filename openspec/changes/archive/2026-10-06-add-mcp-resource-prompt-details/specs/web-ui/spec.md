## MODIFIED Requirements

### Requirement: Keep the capability tabs uniform
The Tools, Resources and Prompts tabs MUST be uniform — each carrying a filter box, a per-row enable toggle and a per-row checkbox with a select-all box in the header, with each row's use in the last 24 hours; while rows are ticked a selection bar replaces the filter with Turn on, Turn off and (on Tools, while tiering is on) Exposure for the ticked rows — and MUST keep that chrome even when the upstream exposes none of that kind, saying so inside the tab rather than as a bare card. A tool row opens to its full description, its input parameters and the name agents see it by. A resource row and a prompt row open the same way, in place under the row and one row at a time: a resource to its description, name, MIME type and the address agents read it by, with **Read content** reading it from the server now (JSON laid out, text past 64 KB cut and said so, a binary body named by its type and size and never shown); a prompt to its description, its arguments as fields (required ones marked, each with its description) and the name agents see, with **Get prompt** showing the messages the server fills it to, offered once every required argument is filled. An error the server answers with reads in place of the content. The server list likewise carries a search box and a Reach filter (every server, or those reaching one agent) and a client-side pager so a large vault stays navigable; the skills list works the same way.

#### Scenario: capability toggle uses the redesigned tab layout
- **GIVEN** a registered MCP server with at least one tool and one resource
- **WHEN** the user opens the server's detail page and clicks the Tools tab
- **THEN** each tool renders as a row with its name, description, and an enabled/disabled switch
- **AND** toggling a tool's switch persists the change (capability preference) and re-fetches the tool list
- **AND** the same flow works for the Resources tab and the Prompts tab

#### Scenario: resource capability toggle works via the Resources tab
- **GIVEN** a registered MCP server that exposes at least one resource URI
- **WHEN** the user navigates to the Resources tab and disables a resource via its toggle
- **THEN** the resource switch reflects the disabled state

#### Scenario: prompt capability toggle works via the Prompts tab
- **GIVEN** a registered MCP server that exposes at least one prompt
- **WHEN** the user navigates to the Prompts tab and disables a prompt via its toggle
- **THEN** the prompt switch reflects the disabled state

#### Scenario: capability search box narrows the tool list
- **GIVEN** a registered MCP server with multiple tools
- **WHEN** the user types a partial name in the capability search box on the Tools tab
- **THEN** only matching tools remain visible and non-matching tools are hidden

#### Scenario: a resource row opens to its details and reads its content
- **GIVEN** a server offering a JSON resource
- **WHEN** the user opens its row on the Resources tab and presses Read content
- **THEN** the details show its MIME type and the address agents read it by, and nothing is read before the press
- **AND** after the press its content shows laid out as JSON

#### Scenario: a prompt row opens to its arguments and fills the prompt
- **GIVEN** a server offering a prompt with one required argument
- **WHEN** the user opens its row on the Prompts tab
- **THEN** the argument shows as a field marked required, and Get prompt waits until it is filled
- **AND** once filled, Get prompt shows the messages the server returns, each with its role

### Requirement: Show the built-in coffer server read-only
The MCP servers list MUST end with a Built-in group holding Coffer's own
`coffer` server, and its detail MUST be read-only: no Test, Edit, Delete, Turn
off or ⋯ menu, its reach a fixed "All connected agents", a note that it cannot
be edited or removed because it is how agents reach the other servers, its
calls in the last 24 hours, and its tools, always on, with the names agents see
them by. On its Tools tab a tool row opens the way a registered server's does, to
its full description, its input parameters and the name agents see it by. It is described by the daemon ([mcp-gateway](../mcp-gateway/spec.md)
"Describe the built-in coffer server") and is not a registered resource.

#### Scenario: the built-in coffer server is listed last and opens read-only
- **GIVEN** the MCP servers page with one registered server
- **WHEN** it renders and the user opens the Built-in `coffer` row
- **THEN** the row sits under Built-in after the registered servers and its detail shows its tools with no Test, Edit or ⋯ menu

#### Scenario: a built-in tool row opens to its details
- **GIVEN** the built-in `coffer` server's Tools tab
- **WHEN** the user opens the `search_tools` row
- **THEN** it shows the tool's input parameters and the name `coffer__search_tools`
