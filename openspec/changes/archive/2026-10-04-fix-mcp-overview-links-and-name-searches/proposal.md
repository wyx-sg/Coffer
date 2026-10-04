## Why

Three things on an MCP server's page sent the reader the wrong way, and list
searches matched more than they show. The Overview's 24-hour block linked to the
Activity page although the server has its own Invocations tab; the Requires
section named a secret by the header that carries it (`Authorization`) rather
than by the secret itself, and its link opened the whole Secrets list; and the
secret picker in an edit dialog closed the moment it opened, so no secret could
be chosen. Searching a server's tools for "test" listed every tool whose
description said "test" somewhere past the truncated line.

## What Changes

- The Overview's **Last 24 hours** links **View invocations** to the server's own
  Invocations tab.
- **Requires** names each secret by its own name, with the carrying setting as a
  tooltip; **View in Secrets** opens `/secrets?q=<name>`.
- The secret menu stays open inside a dialog: the Radix dialog, popover, select
  and tooltip packages share one focus-scope and dismissable-layer copy, and a
  tooltip opens on keyboard focus only, so a dialog's first control does not
  show one when the dialog opens.
- List searches match names only (titles too, where an item has one).

## Capabilities

### Modified Capabilities
- `web-ui`: Overview links, Requires secret rows, name-only list searches.
- `mcp-gateway`: the Tools, Resources and Prompts tabs search names.
- `agent-registry`: the agent's own hooks search the command.

## Impact

Frontend only: `McpOverviewTab`, `McpRequires`, the list filters, the tooltip
trigger, and `@radix-ui/react-dialog`, `-popover`, `-select` versions.
