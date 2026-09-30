---
title: coffer vault
description: "The vault's history: versions, diffs, restore, and hand edits that were refused."
---

# coffer vault

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

The vault's history: versions, diffs, restore, and hand edits that were refused.

## vault history

```sh
coffer vault history [OPTIONS] PATH
```

List a file's or folder's versions, newest first, with who wrote each.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file, or a folder ending in / |
| `--limit` | 选项 | integer | `20` | How many versions |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## vault diff

```sh
coffer vault diff [OPTIONS] PATH VERSION
```

Print what one version did to a file, as a unified diff.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file |
| `VERSION` | 参数 | text | 必填 | The version (from `history`) |

## vault show

```sh
coffer vault show [OPTIONS] PATH VERSION
```

Print a file's content as one version left it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file |
| `VERSION` | 参数 | text | 必填 | The version (from `history`) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## vault restore

```sh
coffer vault restore [OPTIONS] PATH VERSION
```

Put one version back, as a new version. A folder is restored whole: files the version did not have are removed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | A vault file, or a folder ending in / |
| `VERSION` | 参数 | text | 必填 | The version to put back (from `history`) |
| `--yes, -y` | 选项 | 开关 |  | Do not ask |

## vault problems

```sh
coffer vault problems [OPTIONS]
```

List hand edits that were refused: still on disk, not in effect until fixed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
