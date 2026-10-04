---
title: coffer cli
description: "Read the command-line tools Coffer manages."
pageClass: cli-ref
---

# coffer cli

Read the command-line tools Coffer manages.

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer cli --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`cli list`](#cli-list) | List every command-line tool Coffer manages, problems first. |

## cli list

List every command-line tool Coffer manages, problems first.

The tools Coffer runs itself (git), the tools skills require, the launchers MCP servers start with, and the tools the developer added by hand: what each is for, who needs it, and whether it is ready, missing, outdated or logged out on this machine as of Coffer's last check. --json carries the full rows, including the prompt for an agent to install, update or log in to one that needs it.

<p class="cli-label">Synopsis</p>

```sh
coffer cli list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
