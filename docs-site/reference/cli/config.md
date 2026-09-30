---
title: coffer config
description: "Read and change Coffer's settings (coffer config list shows every key)"
---

# coffer config

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer config [OPTIONS] COMMAND [ARGS]...
```

Read and change Coffer's settings (coffer config list shows every key)

## config list

```sh
coffer config list [OPTIONS] [PREFIX]
```

List every key with its value, its default, its type and its help.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PREFIX` | argument | text | `""` | Only keys starting with this, e.g. engine. |
| `--json` | option | flag |  | JSON output for scripts |

## config get

```sh
coffer config get [OPTIONS] KEY
```

Print a setting's current value.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `KEY` | argument | text | required | Setting key |
| `--json` | option | flag |  | JSON output for scripts |

## config set

```sh
coffer config set [OPTIONS] KEY VALUE
```

Change a setting; the value is checked against the key's type first.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `KEY` | argument | text | required | Setting key |
| `VALUE` | argument | text | required | New value (see the key's type in config list) |

## config unset

```sh
coffer config unset [OPTIONS] KEY
```

Return a setting to its default.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `KEY` | argument | text | required | Setting key |
