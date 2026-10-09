## Why

On an MCP server's page only a tool row opens to its details. A resource or prompt row shows a
one-line, cut-off description and nothing else: there is no way to see a resource's type or
content, or what a prompt takes and what it fills to, without going through an agent.

## What Changes

- A Resources or Prompts row opens the way a tool row does: in place under the row, one row at
  a time, with a chevron by its name. Tools keep their behaviour.
- A resource's details show its description, name, MIME type and the address agents read it by,
  and a **Read content** button that reads it from the server now: text (JSON laid out) in a box
  that scrolls, cut at 64 KB and said so; a binary body named by its type and size, never shown.
- A prompt's details show its description, its arguments (required ones marked, with each
  argument's description) as fields, the name agents see, and a **Get prompt** button that asks
  the server for the messages those values make; it waits until every required argument is
  filled.
- The built-in `coffer` server's tool rows open the same way on its Tools tab (full description,
  input parameters, the name agents see); the daemon now sends each built-in tool's input schema.
- The daemon serves both reads to the page: `POST /resources/mcp_server/{uid}/resources/read`
  and `/prompts/get`. An error the server answers with comes back in the body; nothing is logged
  as an agent's invocation. `coffer mcp resource read` and `coffer mcp prompt get` call them.

## Impact

- Backend: `application/mcp/capability_preview.py`, a public `CapabilityDiscovery.request` that
  keeps an upstream's own error answer from costing the connection, new routes.
- CLI: `mcp resource read`, `mcp prompt get`.
- Frontend: capability rows open to details (`McpCapabilityRow`, `McpResourceDetail`,
  `McpPromptDetail`, `McpPreviewResult`).
- Specs: mcp-gateway, web-ui. Docs: MCP servers guide (en, zh). Canvas: Capabilities 4.1.11, 4.1.12.
