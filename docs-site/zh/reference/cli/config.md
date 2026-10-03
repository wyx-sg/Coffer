---
title: coffer config
description: "Read and change Coffer's settings (coffer config list shows every key)"
pageClass: cli-ref
---

# coffer config

Read and change Coffer's settings (coffer config list shows every key)

```sh
coffer config [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer config --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`config list`](#config-list) | List every key with its value, its default, its type and its help. |
| [`config get`](#config-get) | Print a setting's current value. |
| [`config set`](#config-set) | Change a setting; the value is checked against the key's type first. |
| [`config unset`](#config-unset) | Return a setting to its default. |

## config list

List every key with its value, its default, its type and its help.

<p class="cli-label">概要</p>

```sh
coffer config list [OPTIONS] [PREFIX]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PREFIX` <span class="cli-chip">参数</span> | text | `""` | Only keys starting with this, e.g. engine. |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## config get

Print a setting's current value.

<p class="cli-label">概要</p>

```sh
coffer config get [OPTIONS] KEY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">参数</span> | text | 必填 | Setting key |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## config set

Change a setting; the value is checked against the key's type first.

<p class="cli-label">概要</p>

```sh
coffer config set [OPTIONS] KEY VALUE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">参数</span> | text | 必填 | Setting key |
| `VALUE` <span class="cli-chip">参数</span> | text | 必填 | New value (see the key's type in config list) |

## config unset

Return a setting to its default.

<p class="cli-label">概要</p>

```sh
coffer config unset [OPTIONS] KEY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">参数</span> | text | 必填 | Setting key |
