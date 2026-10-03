---
title: coffer adopt
description: "Bring one scanned item under Coffer's management"
pageClass: cli-ref
---

# coffer adopt

Bring one scanned item under Coffer's management

```sh
coffer adopt [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer adopt --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`adopt skill`](#adopt-skill) | Move an unmanaged skill folder into Coffer's master store and link it back. |
| [`adopt mcp`](#adopt-mcp) | Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent. |

## adopt skill

Move an unmanaged skill folder into Coffer's master store and link it back.

<p class="cli-label">Synopsis</p>

```sh
coffer adopt skill [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | The folder path the scan printed |

## adopt mcp

Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent.

<p class="cli-label">Synopsis</p>

```sh
coffer adopt mcp [OPTIONS] AGENT:ENTRY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT:ENTRY` <span class="cli-chip">argument</span> | text | required | The ref the scan printed |
| `--name` <span class="cli-chip">option</span> | text |  | Register the server under this name |
| `--source` <span class="cli-chip">option</span> | text |  | Config-file key when the entry is in several files |
| `--secret` <span class="cli-chip">option</span> | text (repeatable) |  | KEY=SECRET_REF for a secret-like env/header key (repeatable) |
