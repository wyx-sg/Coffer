## Why

The Add server dialog carried a second way in, **Import from your agents**,
that duplicated what each agent's **MCP servers** tab already does (adopt a
direct entry into Coffer). Two places to import the same entries was one too
many; the person asked for importing to live on the agent's page only.

## What Changes

- The Add server dialog drops its "Already have them elsewhere? Import from
  your agents" line and the import review it opened. It adds the servers the
  person pastes or types, nothing else.
- **BREAKING (web UI only)**: the batch import review (change preview of the
  daemon's import plan, then apply) is no longer offered on any page.
  `POST /agents/mcp-import/apply` and `coffer agent mcp-import apply` stay.
- The MCP servers page's first-run card still lists the agents' own servers,
  per agent, with the file each sits in; each row now opens that agent's
  **MCP servers** tab instead of a Review and import button.

## Capabilities

### Modified Capabilities
- `web-ui`: "Add MCP servers by pasting them into one box" no longer carries Import from
  agents; "Review an import from the agents before it is applied" is removed.

## Impact

Frontend only (`AddMcpServerDialog`, `PasteStep`, `McpFirstRun`,
`ResourcesPage`, i18n), the user guides, and the CLI coverage labels of the
two import routes. No backend behaviour changes.
