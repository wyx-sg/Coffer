## Why

The Custom tools page lagged the MCP servers and Skills pages it sits beside:
its list could not be narrowed to one agent or acted on in bulk, and a group's
tools table had no search and put **Add request** below the last row, out of
view once a group has many tools. Each tool also carried a reach of its own,
which repeated the group's reach in every row for a case the tool's on/off
switch and a second group already cover.

## What Changes

- **BREAKING** A custom tool has no reach of its own: every tool that is on
  reaches exactly the agents its group reaches. The route that set or cleared one
  tool's reach and `~/.coffer/local/tool-reach.json` are removed, and the tools
  table loses its reach column.
- The Custom tools list accepts `?agent=<uid>` and names the agent in a removable
  filter, as the MCP servers and Skills lists do.
- Groups can be ticked and acted on together: a selection bar with Reach, Delete
  and a clear, a select-all row, and Esc to clear.
- An agent's MCP servers tab carries a From Coffer row for custom-tool groups,
  linking to `/custom-tools?agent=<uid>`; the MCP servers row counts registered
  servers only.
- A group's tools table has a search by tool name and **Add request** in one row
  above the table.

## Capabilities

### Modified Capabilities

- `mcp-gateway` — a custom tool's reach is its group's.
- `web-ui` — the Custom tools list's agent filter and multi-select; the tools
  table's search and Add request position; the inherited reach control is gone.
- `agent-registry` — the custom-tool From Coffer row on the MCP servers tab.

## Impact

Backend custom-tool routes, schemas, views and gateway gate; the mcp-gateway
OpenAPI contract and the generated frontend types; the Custom tools page and
the agent MCP servers tab; docs-site custom tools, web UI, architecture and
filesystem pages (en + zh); the Capabilities and Agents design canvases.
