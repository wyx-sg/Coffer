## Why

The Capabilities canvas (MCP servers, Custom tools, Skills) is final. Three of its decisions need backend support the code did not have, and several boards and prototypes drew states the pages did not yet show:

- The Add server dialog tested a server only after it was registered, because no route could test a config that was not saved.
- Import from your agents adopted entries one by one without showing what it would change in each agent's config file.
- Coffer's own `coffer` MCP server, which every connected agent reaches, did not appear on the MCP servers page.

## What Changes

- A route tests an unsaved MCP server config: it starts a stdio server for the length of the test or connects to an HTTP one, lists its tools, keeps the tail of its stderr, then discards everything and persists nothing. A typed URL goes through the SSRF guard first, the test has a hard time limit, and a stdio child's whole process group is stopped when it ends. The Add dialog shows the result, tools found or the error with the stderr tail, before Add server.
- A dry-run route plans an import from the agents: which servers Coffer adds, which entries merge into one server or duplicate a server Coffer already has, and a per-file diff of each agent config file it will edit. A second route applies the same plan. The Import from your agents dialog shows the plan before anything is written.
- The MCP servers list shows Coffer's own `coffer` server last, under Built-in, read-only, with a read-only detail built from the gateway's built-in tool list. It is not a registered resource.
- The MCP servers, Custom tools and Skills pages are brought in line with every board and prototype of the canvas.

## Capabilities

### New Capabilities

### Modified Capabilities
- `mcp-gateway`: testing an unsaved server config; describing the built-in `coffer` server.
- `agent-registry`: planning and applying an import of agents' direct MCP entries.
- `web-ui`: the MCP servers, Custom tools and Skills pages as the final canvas draws them.

## Impact

- Backend: MCP test and import routes, the gateway's built-in server description.
- Frontend: the MCP servers, Custom tools and Skills pages.
- Docs: the MCP servers, Custom tools and Skills guides and architecture pages; the generated references.
- Design canvas: none; the canvas is the target.
