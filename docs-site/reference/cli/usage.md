---
title: coffer usage
description: "Model usage through Coffer's proxy, and subscription quota"
pageClass: cli-ref
---

# coffer usage

Model usage through Coffer's proxy, and subscription quota

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
| [`usage quota`](#usage-quota) | Show each subscription agent's official remaining quota. |
| [`usage statusline`](#usage-statusline) | Opt-in Claude Code statusLine wrapper: forward rate limits, then chain. |

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

## usage quota

Show each subscription agent's official remaining quota.

<p class="cli-label">Synopsis</p>

```sh
coffer usage quota [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--refresh` <span class="cli-chip">option</span> | flag |  | Read Codex's windows now |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that has your agent set up the statusline wrapper |

## usage statusline

Opt-in Claude Code statusLine wrapper: forward rate limits, then chain.

<p class="cli-label">Synopsis</p>

```sh
coffer usage statusline [OPTIONS] [COMMAND]...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `COMMAND` <span class="cli-chip">argument</span> | text (variadic) |  | The original statusLine command to run after forwarding |
