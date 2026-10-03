---
title: coffer vault
description: "The vault's history: versions, diffs, restore, and hand edits that were refused."
pageClass: cli-ref
---

# coffer vault

The vault's history: versions, diffs, restore, and hand edits that were refused.

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer vault --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`vault history`](#vault-history) | List a file's or folder's versions, newest first, with who wrote each. |
| [`vault diff`](#vault-diff) | Print what one version did to a file, as a unified diff. |
| [`vault show`](#vault-show) | Print a file's content as one version left it. |
| [`vault restore`](#vault-restore) | Put one version back, as a new version. |
| [`vault problems`](#vault-problems) | List hand edits that were refused: still on disk, not in effect until fixed. |

## vault history

List a file's or folder's versions, newest first, with who wrote each.

<p class="cli-label">概要</p>

```sh
coffer vault history [OPTIONS] PATH
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | A vault file, or a folder ending in / |
| `--limit` <span class="cli-chip">选项</span> | integer | `20` | How many versions |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## vault diff

Print what one version did to a file, as a unified diff.

<p class="cli-label">概要</p>

```sh
coffer vault diff [OPTIONS] PATH VERSION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | A vault file |
| `VERSION` <span class="cli-chip">参数</span> | text | 必填 | The version (from `history`) |

## vault show

Print a file's content as one version left it.

<p class="cli-label">概要</p>

```sh
coffer vault show [OPTIONS] PATH VERSION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | A vault file |
| `VERSION` <span class="cli-chip">参数</span> | text | 必填 | The version (from `history`) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## vault restore

Put one version back, as a new version. A folder is restored whole: files the version did not have are removed.

<p class="cli-label">概要</p>

```sh
coffer vault restore [OPTIONS] PATH VERSION
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | A vault file, or a folder ending in / |
| `VERSION` <span class="cli-chip">参数</span> | text | 必填 | The version to put back (from `history`) |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

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
