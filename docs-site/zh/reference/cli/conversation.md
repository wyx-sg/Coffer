---
title: coffer conversation
description: "Conversations: rename, stop a turn, delete (list: agent session all)."
pageClass: cli-ref
---

# coffer conversation

Conversations: rename, stop a turn, delete (list: agent session all).

```sh
coffer conversation [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer conversation --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`conversation rename`](#conversation-rename) | Rename a conversation. |
| [`conversation interrupt`](#conversation-interrupt) | Stop the turn in progress. |
| [`conversation delete`](#conversation-delete) | Delete a conversation. |

## conversation rename

Rename a conversation. Body: title.

<p class="cli-label">概要</p>

```sh
coffer conversation rename [OPTIONS] ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">参数</span> | text | 必填 | id |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## conversation interrupt

Stop the turn in progress.

<p class="cli-label">概要</p>

```sh
coffer conversation interrupt [OPTIONS] ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">参数</span> | text | 必填 | id |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## conversation delete

Delete a conversation.

<p class="cli-label">概要</p>

```sh
coffer conversation delete [OPTIONS] ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ID` <span class="cli-chip">参数</span> | text | 必填 | id |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
