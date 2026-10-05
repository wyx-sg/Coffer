---
title: coffer vault
description: "The vault's history and the hand edits it refused."
pageClass: cli-ref
---

# coffer vault

The vault's history and the hand edits it refused.

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer vault --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`vault problems`](#vault-problems) | List hand edits that were refused: still on disk, not in effect until fixed. |
| [`vault history`](#vault-history) | A vault path's versions, newest first, each with its writer. |
| [`vault diff`](#vault-diff) | One version's diff. |
| [`vault restore`](#vault-restore) | Write a version back as a new commit. |

## vault problems

List hand edits that were refused: still on disk, not in effect until fixed.

<p class="cli-label">概要</p>

```sh
coffer vault problems [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## vault history

A vault path's versions, newest first, each with its writer.

<p class="cli-label">概要</p>

```sh
coffer vault history [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">选项</span> | text |  | A path under the vault |
| `--limit` <span class="cli-chip">选项</span> | integer |  |  |
| `--cursor` <span class="cli-chip">选项</span> | text |  |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## vault diff

One version's diff.

<p class="cli-label">概要</p>

```sh
coffer vault diff [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--path` <span class="cli-chip">选项</span> | text |  |  |
| `--version` <span class="cli-chip">选项</span> | text |  |  |
| `--against` <span class="cli-chip">选项</span> | text |  | previous or current |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## vault restore

Write a version back as a new commit. Body: path, version, expected_current.

<p class="cli-label">概要</p>

```sh
coffer vault restore [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
