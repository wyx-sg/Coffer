## ADDED Requirements

### Requirement: Preview a resource or a prompt from the server page
The daemon MUST read one of a registered server's resources, and fill one of its prompts with given arguments, for the server page's row details: `POST /resources/mcp_server/{uid}/resources/read` (a `uri`) and `POST /resources/mcp_server/{uid}/prompts/get` (a `name` and its `arguments`), over the same connection the capability listings use. A text body MUST be cut at 64 KB and marked cut; a binary body MUST be described by its MIME type and size and its bytes not sent. An error the server answers with MUST come back in the body's `error`, with no contents, and MUST NOT close the connection; a server that cannot be reached is `UPSTREAM_UNAVAILABLE`. A preview is the owner looking, not an agent calling: it MUST NOT be recorded as an invocation, and it works on a row that is switched off. `coffer mcp resource read` and `coffer mcp prompt get` call the same routes.

#### Scenario: read a resource from its row
- **GIVEN** a registered server offering the text resource `file:///tmp/a.txt`
- **WHEN** its content is read through `POST /resources/mcp_server/{uid}/resources/read`
- **THEN** the answer carries the resource's text with its MIME type, not cut

#### Scenario: fill a prompt from its row
- **GIVEN** a registered server offering the prompt `summarise`
- **WHEN** it is filled through `POST /resources/mcp_server/{uid}/prompts/get` with an argument
- **THEN** the answer carries the prompt's description and its messages, each with its role

## MODIFIED Requirements

### Requirement: Describe the built-in coffer server
The daemon MUST describe Coffer's own `coffer` MCP server read-only, so the MCP servers page can show it beside the servers the person added: its name, its transport (Streamable HTTP), the endpoint URL agents connect to on the bound port, that it is healthy while the daemon answers, that it reaches every connected agent (with the uids of the agents connected now), its tools from the gateway's built-in tool list as agents see them (only the tools of switched-on features, each with its `coffer__` name and its input schema), and the last 24 hours of its calls in the shape a registered server's page reads. It is not a registered resource: it has no row, and nothing about it can be edited or removed.

#### Scenario: the built-in coffer server is described read-only
- **GIVEN** the daemon is running with one agent connected and a built-in tool called once
- **WHEN** the MCP servers page reads the built-in server
- **THEN** it is named `coffer` with the endpoint `http://127.0.0.1:<port>/mcp`, reaches that agent, lists `search_tools` as `coffer__search_tools`, and counts the one call
- **AND** no `mcp_server` resource named `coffer` exists
