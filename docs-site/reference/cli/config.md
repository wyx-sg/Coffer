---
title: coffer config
description: "Daemon settings read before it binds (work while it is down)."
pageClass: cli-ref
---

# coffer config

Daemon settings read before it binds (work while it is down).

```sh
coffer config [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer config --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`config list`](#config-list) | List every key with its value, its default, its type and its help. |
| [`config get`](#config-get) | Print a setting's current value. |
| [`config set`](#config-set) | Change a setting; the value is checked against the key's type first. |
| [`config unset`](#config-unset) | Return a setting to its default. |

## config list

List every key with its value, its default, its type and its help.

<p class="cli-label">Synopsis</p>

```sh
coffer config list [OPTIONS] [PREFIX]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PREFIX` <span class="cli-chip">argument</span> | text | `""` | Only keys starting with this, e.g. daemon. |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## config get

Print a setting's current value.

<p class="cli-label">Synopsis</p>

```sh
coffer config get [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | Setting key |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## config set

Change a setting; the value is checked against the key's type first.

<p class="cli-label">Synopsis</p>

```sh
coffer config set [OPTIONS] KEY VALUE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | Setting key |
| `VALUE` <span class="cli-chip">argument</span> | text | required | New value (see the key's type in config list) |

## config unset

Return a setting to its default.

<p class="cli-label">Synopsis</p>

```sh
coffer config unset [OPTIONS] KEY
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">argument</span> | text | required | Setting key |
