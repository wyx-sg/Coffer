---
title: coffer scan
description: "List what agents hold that Coffer does not manage: agents, skills, MCP entries."
---

# coffer scan

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer scan [OPTIONS]
```

List what agents hold that Coffer does not manage: agents, skills, MCP entries.

With --ref, show that one row in full: an MCP entry's whole configuration (secret values withheld) or an unmanaged skill's metadata.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--agent` | option | text |  | Only what this agent holds |
| `--ref` | option | text |  | Show one row in full: a type, a folder path or &lt;agent&gt;:&lt;entry&gt; |
| `--source` | option | text |  | With --ref on an mcp row: the config-file key |
| `--json` | option | flag |  | JSON output for scripts |
