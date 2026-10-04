## MODIFIED Requirements

### Requirement: Select several MCP servers from the list
A MCP server's row MUST show its checkbox on hover or focus, and on every row
once any is ticked. Ticking a row puts the selection bar at the top of the list:
"N of M selected", **Reach** (the bulk control of "Apply reach to a whole
selection"), **Delete** and a clear (×); a select-all row appears and ticks every
listed server. The built-in server has no checkbox and is not counted, and Esc
clears the selection. Over the list sit its search and a Reach filter — every
server, or only the servers that reach one chosen agent — which reads and writes
the same `agent` query parameter the agent's MCP servers tab links with; the
built-in server reaches every agent and stays listed.

#### Scenario: ticking a server puts the selection bar at the top
- **GIVEN** the MCP servers list
- **WHEN** the user ticks one row
- **THEN** the bar at the top reads "1 of N selected" with Reach, Delete and a clear control

#### Scenario: the Reach filter narrows the servers to one agent
- **GIVEN** a server on for every agent and one limited to Codex
- **WHEN** the user chooses Claude Code in the MCP servers list's Reach filter
- **THEN** only the server on for every agent and the built-in server are listed, and the address carries `?agent=<Claude Code's uid>`

### Requirement: Keep the capability tabs uniform
The Tools, Resources and Prompts tabs MUST be uniform — each carrying its count of how many are on, a filter box, All on · All off and a per-row enable toggle, with each row's use in the last 24 hours — and MUST keep that chrome even when the upstream exposes none of that kind, saying so inside the tab rather than as a bare card. A tool row opens to its full description, its input parameters and the name agents see it by. The server list likewise carries a search box and a Reach filter (every server, or those reaching one agent) and a client-side pager so a large vault stays navigable; the skills list works the same way.

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
