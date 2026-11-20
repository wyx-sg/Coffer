# OpenCode Gets Its MCP Entry in the 1.x Shape

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), spec agent-registry/opencode

## Context

OpenCode ships a 1.x line (`opencode-ai`, 1.19) and a 2.x line
(`@opencode/cli`, 2.3) side by side, reading the same
`~/.config/opencode/opencode.json`. They spell an MCP server differently:

- 1.x: `"mcp": {"<name>": {"type": "local", "command": [...], "enabled": true}}`
- 2.x: `"mcp": {"servers": {"<name>": {"type": "local", "command": [...]}}}`, with
  `disabled` instead of `enabled`.

The 2.x migration guide says 1.x configs still load, and that an entry without
`type` is ignored with a warning.

## Options Considered

### Option A — Write the 1.x shape, with `type` (chosen)

`mcp.coffer = {"type": "local", "command": [<shim>, "--agent-uid", <uid>]}`.

- Pro: both lines read it, so Coffer need not know which one is installed.
- Con: a 2.x person sees one entry outside `mcp.servers`.

### Option B — Probe the version and write the matching shape

- Pro: each file stays in its own line's shape.
- Con: two code paths, and a version probe on every write; a person running
  both lines (the 2.x installer adds an `opencode2` alias for that) would see
  Coffer's entry flip between shapes.

### Option C — Write the 2.x shape only

- Con: 1.x reads `servers` as a server named "servers" with no command and
  never sees Coffer.

## Decision

Option A. Listing reads both places: entries directly under `mcp`, and the
2.x `mcp.servers` map, which removing an entry also reaches.

## Consequences

- If a future OpenCode release stops loading the 1.x shape, the CI smoke
  check (`opencode mcp list`) fails and the shape is revisited.
- A file named `opencode.jsonc` is used when it is the only one; a file with
  comments does not parse as JSON, and its tabs show the parse-error state
  instead of losing the comments on a write.
