## Why

The MCP servers list could be narrowed to one agent only by arriving from that
agent's MCP servers tab (`?agent=`); nothing on the page itself set it. The Skills
list got its Reach filter back; the MCP servers list should read the same.

## What Changes

- The MCP servers list carries the Reach filter under its search: All, or one
  agent. It reads and writes `?agent=`, so a link from an agent's tab lands with
  the agent chosen. The built-in `coffer` server reaches every agent and stays.
- The Skills list's filter becomes the shared `AgentReachFilter`, used by both
  lists; the removable "Agent: <name>" pill it replaced is gone.

## Capabilities

### Modified Capabilities
- `web-ui`: the MCP servers list has a Reach filter.

## Impact

Frontend only: `McpServerList`, `SkillLibrary`, `components/reach/AgentReachFilter`.
