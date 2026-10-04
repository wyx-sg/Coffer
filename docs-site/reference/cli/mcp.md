---
title: coffer mcp
description: "Check an MCP server"
pageClass: cli-ref
---

# coffer mcp

Check an MCP server

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer mcp --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`mcp test`](#mcp-test) | Re-query a server's capabilities, then report whether it answers. |

## mcp test

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

<p class="cli-label">Synopsis</p>

```sh
coffer mcp test [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Server name |
| `--prompt` <span class="cli-chip">option</span> | flag |  | On a failure, also print the prompt to give your agent |
