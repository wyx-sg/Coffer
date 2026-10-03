---
title: coffer discard
description: "Remove one scanned item from the agent that holds it"
pageClass: cli-ref
---

# coffer discard

Remove one scanned item from the agent that holds it

```sh
coffer discard [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer discard --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`discard skill`](#discard-skill) | Delete an unmanaged skill folder from the agent's skill location (from disk). |
| [`discard mcp`](#discard-mcp) | Remove an MCP entry from the agent's own config file (a .bak is kept). |

## discard skill

Delete an unmanaged skill folder from the agent's skill location (from disk).

<p class="cli-label">Synopsis</p>

```sh
coffer discard skill [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | The folder path the scan printed |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## discard mcp

Remove an MCP entry from the agent's own config file (a .bak is kept).

<p class="cli-label">Synopsis</p>

```sh
coffer discard mcp [OPTIONS] AGENT:ENTRY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `AGENT:ENTRY` <span class="cli-chip">argument</span> | text | required | The ref the scan printed |
| `--source` <span class="cli-chip">option</span> | text |  | Config-file key when the entry is in several files |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |
