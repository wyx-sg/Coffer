---
title: coffer config
description: "Read and change Coffer's settings (coffer config list shows every key)"
---

# coffer config

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer config [OPTIONS] COMMAND [ARGS]...
```

Read and change Coffer's settings (coffer config list shows every key)

## config list

```sh
coffer config list [OPTIONS] [PREFIX]
```

List every key with its value, its default, its type and its help.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PREFIX` | 参数 | text | `""` | Only keys starting with this, e.g. engine. |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## config get

```sh
coffer config get [OPTIONS] KEY
```

Print a setting's current value.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## config set

```sh
coffer config set [OPTIONS] KEY VALUE
```

Change a setting; the value is checked against the key's type first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |
| `VALUE` | 参数 | text | 必填 | New value (see the key's type in config list) |

## config unset

```sh
coffer config unset [OPTIONS] KEY
```

Return a setting to its default.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `KEY` | 参数 | text | 必填 | Setting key |
