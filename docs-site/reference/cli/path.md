---
title: coffer path
description: "Where Coffer's log files and skill working files live"
pageClass: cli-ref
---

# coffer path

Where Coffer's log files and skill working files live

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer path --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`path logs`](#path-logs) | The log directory and the daemon.log in it (COFFER_LOG_DIR moves both). |
| [`path skill-data`](#path-skill-data) | The directory skill scripts write logs, journals and temp files under. |

## path logs

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

<p class="cli-label">Synopsis</p>

```sh
coffer path logs [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by name |

## path skill-data

The directory skill scripts write logs, journals and temp files under.

<p class="cli-label">Synopsis</p>

```sh
coffer path skill-data [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON object keyed by name |
