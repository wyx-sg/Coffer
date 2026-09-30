---
title: coffer discard
description: "Remove one scanned item from the agent that holds it"
---

# coffer discard

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer discard [OPTIONS] COMMAND [ARGS]...
```

Remove one scanned item from the agent that holds it

## discard skill

```sh
coffer discard skill [OPTIONS] PATH
```

Delete an unmanaged skill folder from the agent's skill location (from disk).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | The folder path the scan printed |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## discard mcp

```sh
coffer discard mcp [OPTIONS] AGENT:ENTRY
```

Remove an MCP entry from the agent's own config file (a .bak is kept).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | argument | text | required | The ref the scan printed |
| `--source` | option | text |  | Config-file key when the entry is in several files |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |
