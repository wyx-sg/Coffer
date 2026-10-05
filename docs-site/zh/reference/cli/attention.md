---
title: coffer attention
description: "What needs you (the Overview list): list, ignore, un-ignore."
pageClass: cli-ref
---

# coffer attention

What needs you (the Overview list): list, ignore, un-ignore.

```sh
coffer attention [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer attention --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`attention list`](#attention-list) | What needs you, each with its fix or its hand-off prompt. |
| [`attention ignore`](#attention-ignore) | Stop listing an informational item. |
| [`attention unignore`](#attention-unignore) | List an ignored item again. |

## attention list

What needs you, each with its fix or its hand-off prompt.

<p class="cli-label">概要</p>

```sh
coffer attention list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## attention ignore

Stop listing an informational item.

<p class="cli-label">概要</p>

```sh
coffer attention ignore [OPTIONS] KEY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">参数</span> | text | 必填 | key |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## attention unignore

List an ignored item again.

<p class="cli-label">概要</p>

```sh
coffer attention unignore [OPTIONS] KEY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` <span class="cli-chip">参数</span> | text | 必填 | key |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
