---
title: coffer adopt
description: "Bring one scanned item under Coffer's management"
---

# coffer adopt

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer adopt [OPTIONS] COMMAND [ARGS]...
```

Bring one scanned item under Coffer's management

## adopt skill

```sh
coffer adopt skill [OPTIONS] PATH
```

Move an unmanaged skill folder into Coffer's master store and link it back.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | The folder path the scan printed |

## adopt mcp

```sh
coffer adopt mcp [OPTIONS] AGENT:ENTRY
```

Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | argument | text | required | The ref the scan printed |
| `--name` | option | text |  | Register the server under this name |
| `--source` | option | text |  | Config-file key when the entry is in several files |
| `--secret` | option | text (repeatable) |  | KEY=SECRET_REF for a secret-like env/header key (repeatable) |
