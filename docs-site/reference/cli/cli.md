---
title: coffer cli
description: "Check the command-line tools skills and MCP servers require"
---

# coffer cli

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

Check the command-line tools skills and MCP servers require

## cli list

```sh
coffer cli list [OPTIONS]
```

List every command a skill or MCP server requires, problems first.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## cli show

```sh
coffer cli show [OPTIONS] COMMAND
```

Show one required command: where it is, its version and login state.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | The command, e.g. gh |
| `--json` | option | flag |  | JSON output for scripts |

## cli check

```sh
coffer cli check [OPTIONS] [COMMAND]
```

Probe the required commands again (or one of them).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `[COMMAND]` | argument | text |  | One command only |
| `--json` | option | flag |  | JSON output for scripts |

## cli prompt

```sh
coffer cli prompt [OPTIONS] COMMAND
```

Print the prompt to give your agent for a command that needs you.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text | required | The command, e.g. jq |
| `--json` | option | flag |  | JSON output for scripts |
