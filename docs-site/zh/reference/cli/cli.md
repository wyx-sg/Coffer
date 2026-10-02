---
title: coffer cli
description: "Add and check command-line tools, and read their interface"
---

# coffer cli

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

Add and check command-line tools, and read their interface

## cli list

```sh
coffer cli list [OPTIONS]
```

List every command-line tool — added by hand or required — problems first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli add

```sh
coffer cli add [OPTIONS] COMMAND
```

Add a command-line tool by hand; no skill is needed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | A command name (jq) or the absolute path of an executable |
| `--title` | 选项 | text |  | A display name |
| `--description` | 选项 | text |  | What it is for |
| `--min-version` | 选项 | text |  | Oldest wanted, like "2.40" |
| `--login-check` | 选项 | text |  | A command line that exits 0 when logged in, like "gh auth status" |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli edit

```sh
coffer cli edit [OPTIONS] COMMAND
```

Change a tool you added by hand (only the options you give change).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | A tool you added, e.g. jq |
| `--title` | 选项 | text |  | A display name; '' clears it |
| `--description` | 选项 | text |  | '' clears it |
| `--min-version` | 选项 | text |  | '' clears it |
| `--login-check` | 选项 | text |  | '' clears it |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli rm

```sh
coffer cli rm [OPTIONS] COMMAND
```

Remove a tool you added by hand. A skill that requires it keeps it listed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | A tool you added, e.g. jq |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## cli show

```sh
coffer cli show [OPTIONS] COMMAND [SUBCOMMAND]...
```

Show one command-line tool: where it is, its version, login state and its interface — the options and subcommands its own --help lists.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | The command, e.g. gh |
| `[SUBCOMMAND]...` | 参数 | text（可变个数） |  | Show one subcommand |
| `--tree` | 选项 | 开关 |  | Every command of the tool, one per line |
| `--refresh` | 选项 | 开关 |  | Read the tool's help again |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli check

```sh
coffer cli check [OPTIONS] [COMMAND]
```

Probe the required commands again (or one of them).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `[COMMAND]` | 参数 | text |  | One command only |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli prompt

```sh
coffer cli prompt [OPTIONS] COMMAND
```

Print the prompt to give your agent for a command that needs you.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | The command, e.g. jq |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
