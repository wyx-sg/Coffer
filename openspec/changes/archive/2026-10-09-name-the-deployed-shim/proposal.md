## Why

The `coffer` entry Coffer writes into an agent's MCP config named whichever
shim the daemon happened to find first. A daemon started by the desktop app
found the copy inside `Coffer.app`; one started from a terminal found the
public `~/.coffer/bin/coffer-mcp-shim`; one started by launchd could find any
`coffer-mcp-shim` on its `PATH`. The reconciler compares an entry by its
command, so two daemons that answered differently rewrote each other's
entries, each rewrite leaving a config backup. An entry naming the app bundle
also broke when the app was moved or removed while the CLI stayed. The shim
ADR already promised the public path for an installed build.

The one-folder shim change (#643) moved the app's shim out of
`Contents/MacOS`, so the app's daemon now falls through to the deployed shim.
A daemon whose `PATH` holds another shim still answers differently.

## What Changes

- An installed (frozen) build names the deployed `~/.coffer/bin/coffer-mcp-shim`
  first, right after the `COFFER_MCP_SHIM_PATH` override, whenever it exists.
- A source install keeps the previous search order, so a development daemon
  keeps the shim from its own checkout.

## Capabilities

### Modified Capabilities

- `agent-registry`: "Install Coffer's MCP server into an agent in one action"
  — the order the shim is resolved in.

## Impact

`backend/coffer/application/agent/mcp_service.py` and its unit tests; ADR
[An Installed Daemon Names the Deployed Shim](../../../docs/decisions/an-installed-daemon-names-the-deployed-shim.md)
and [Agents Reach the Gateway Through a stdio Shim](../../../docs/decisions/stdio-shim-bridge.md); the
Agents guide (en/zh).
