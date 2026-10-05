---
title: coffer usage
description: "Model usage and cost."
pageClass: cli-ref
---

# coffer usage

Model usage and cost.

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer usage --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`usage summary`](#usage-summary) | Model usage and cost over a range, grouped. |

## usage summary

Model usage and cost over a range, grouped.

<p class="cli-label">Synopsis</p>

```sh
coffer usage summary [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--range` <span class="cli-chip">option</span> | text |  | 24h, 7d, 30d… |
| `--from` <span class="cli-chip">option</span> | text |  |  |
| `--to` <span class="cli-chip">option</span> | text |  |  |
| `--group-by` <span class="cli-chip">option</span> | text |  | model, agent, connection, day |
| `--agent-type` <span class="cli-chip">option</span> | text |  |  |
| `--connection-uid` <span class="cli-chip">option</span> | text |  |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
