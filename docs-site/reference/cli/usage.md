---
title: coffer usage
description: "Model usage through Coffer's proxy, and subscription quota"
---

# coffer usage

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

Model usage through Coffer's proxy, and subscription quota

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--range` | option | text | `today` | today \| 7d \| 30d \| month \| custom |
| `--from` | option | text |  | First day of a custom range |
| `--to` | option | text |  | Last day of a custom range, inclusive |
| `--by` | option | text | `model` | model \| agent \| day |
| `--agent` | option | text |  | Only requests this agent type sent (claude_code \| codex) |
| `--provider` | option | text |  | Only requests this provider (by name) served |
| `--json` | option | flag |  | JSON output for scripts |
| `--csv` | option | flag |  | CSV output |

## usage requests

```sh
coffer usage requests [OPTIONS]
```

List recent metered requests, newest first.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--limit` | option | integer (1-500) | `20` | Most requests to print |
| `--cursor` | option | text |  | The next_cursor a read printed |
| `--json` | option | flag |  | JSON output for scripts |

## usage quota

```sh
coffer usage quota [OPTIONS]
```

Show each subscription agent's official remaining quota.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--refresh` | option | flag |  | Read Codex's windows now |
| `--json` | option | flag |  | JSON output for scripts |
| `--prompt` | option | flag |  | Print the prompt that has your agent set up the statusline wrapper |

## usage statusline

```sh
coffer usage statusline [OPTIONS] [COMMAND]...
```

Opt-in Claude Code statusLine wrapper: forward rate limits, then chain.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `COMMAND` | argument | text (variadic) |  | The original statusLine command to run after forwarding |
