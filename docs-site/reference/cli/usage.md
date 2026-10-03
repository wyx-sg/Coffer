---
title: coffer usage
description: "Model usage through Coffer's proxy"
pageClass: cli-ref
---

# coffer usage

Model usage through Coffer's proxy

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer usage --help` prints. Add `--help` to any command below to see its options in the terminal.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--range` <span class="cli-chip">option</span> | text | `today` | today \| 7d \| 30d \| month \| custom |
| `--from` <span class="cli-chip">option</span> | text |  | First day of a custom range |
| `--to` <span class="cli-chip">option</span> | text |  | Last day of a custom range, inclusive |
| `--by` <span class="cli-chip">option</span> | text | `model` | model \| agent \| day |
| `--agent` <span class="cli-chip">option</span> | text |  | Only requests this agent type sent (claude_code \| codex) |
| `--provider` <span class="cli-chip">option</span> | text |  | Only requests this provider (by name) served |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
| `--csv` <span class="cli-chip">option</span> | flag |  | CSV output |

## Commands

| Command | What it does |
| --- | --- |
| [`usage requests`](#usage-requests) | List recent metered requests, newest first. |

## usage requests

List recent metered requests, newest first.

<p class="cli-label">Synopsis</p>

```sh
coffer usage requests [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--limit` <span class="cli-chip">option</span> | integer (1-500) | `20` | Most requests to print |
| `--cursor` <span class="cli-chip">option</span> | text |  | The next_cursor a read printed |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
