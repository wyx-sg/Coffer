# DeepSeek Harness's MCP Row Lives in a Block Coffer Owns

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), spec agent-registry/deepseek-harness

## Context

DeepSeek Harness builds its plugin tree from YAML patch layers. An MCP server
is one row of the `@deepseek-ai/dsh-mcp-client` plugin inside an `insert`
patch. The home-level layer `$DSH_HOME/cordis.patch.yml` applies to every
profile and outranks each profile's own layer (`homePatchPath()` in
`apps/cli/src/profile-boot.ts`); its documentation tells users to merge MCP
rows into that file and not to overwrite it.

The file is the person's. It may hold comments and `!!js` expressions
(`cwd: !!js process.cwd()`), which no YAML library in Coffer round-trips:
PyYAML's safe loader refuses the tag, and re-serialising drops comments and
reorders keys. [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md)
requires an edit to keep what it does not own.

## Options Considered

### Option A — Parse and re-serialise the file

- Pro: Coffer could add, edit and remove any row.
- Con: loses comments and `!!js` values, or needs a round-tripping YAML
  library Coffer does not ship (ruamel.yaml) and still re-indents the file.

### Option B — A per-profile file

Write to `profiles/web/cordis.patch.yml`.

- Pro: the file the Web UI's Settings page writes.
- Con: only one profile gets the server (headless and ACP do not), and the
  Web UI rewrites that file, so Coffer would compete with it.

### Option C — A marked block in the home-level patch (chosen)

Coffer's row is one `insert` patch between two marker comments at the end of
`$DSH_HOME/cordis.patch.yml`. An install replaces that block as text; an
uninstall removes it; every other byte is left alone. Reads parse the whole
file with a loader that keeps `!!js` values as strings.

- Pro: every profile gets the server; nothing of the person's is rewritten.
- Con: Coffer cannot edit or remove the person's own MCP rows there. It lists
  them, and removing or importing one is refused with `MCP_ENTRY_NOT_EDITABLE`
  ("edit it in the agent's own file").
- Con: a file whose top level is not a block-style list cannot take an
  appended item; then the install fails with a parse-error message and the
  person adds the row themselves.

## Decision

Option C (`domain/agent/mcp_cordis.py`).

## Consequences

- Import of an agent's own entries skips DeepSeek Harness rows with
  `MCP_ENTRY_NOT_EDITABLE`.
- If DeepSeek Harness changes how patch layers compose, the CI smoke check
  (`dsh --profile web --dump-config`) shows it.
