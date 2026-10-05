---
title: coffer resource
description: "Any resource by uid: show, rename, switch on or off, reach, delete."
pageClass: cli-ref
---

# coffer resource

Any resource by uid: show, rename, switch on or off, reach, delete.

```sh
coffer resource [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer resource --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`resource list`](#resource-list) | Resources of every kind, or of one. |
| [`resource show`](#resource-show) | One resource by uid. |
| [`resource add`](#resource-add) | Register a resource. |
| [`resource update`](#resource-update) | Change a resource. |
| [`resource delete`](#resource-delete) | Delete a resource (the kind's cleanup runs first). |
| [`resource enable`](#resource-enable) | Switch a resource on. |
| [`resource disable`](#resource-disable) | Switch a resource off. |
| [`resource reach`](#resource-reach) | Which agents a resource reaches. |
| [`resource reach show`](#resource-reach-show) | Which agents a resource reaches. |
| [`resource reach set`](#resource-reach-set) | Set the agents a resource reaches. |

## resource list

Resources of every kind, or of one.

<p class="cli-label">概要</p>

```sh
coffer resource list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--kind` <span class="cli-chip">选项</span> | text |  | mcp_server, agent, skill, knowledge, memory, provider, channel |
| `--name` <span class="cli-chip">选项</span> | text |  |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource show

One resource by uid.

<p class="cli-label">概要</p>

```sh
coffer resource show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource add

Register a resource. Body: kind, name, config, description, title.

<p class="cli-label">概要</p>

```sh
coffer resource add [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource update

Change a resource. Body: name, title, description, config.

<p class="cli-label">概要</p>

```sh
coffer resource update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource delete

Delete a resource (the kind's cleanup runs first).

<p class="cli-label">概要</p>

```sh
coffer resource delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource enable

Switch a resource on.

<p class="cli-label">概要</p>

```sh
coffer resource enable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource disable

Switch a resource off.

<p class="cli-label">概要</p>

```sh
coffer resource disable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource reach

Which agents a resource reaches.

<p class="cli-label">概要</p>

```sh
coffer resource reach [OPTIONS] COMMAND [ARGS]...
```

子命令：`show`, `set`。

## resource reach show

Which agents a resource reaches.

<p class="cli-label">概要</p>

```sh
coffer resource reach show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## resource reach set

Set the agents a resource reaches. Body: scope ({agents: [uid…]} or null for every agent).

<p class="cli-label">概要</p>

```sh
coffer resource reach set [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
