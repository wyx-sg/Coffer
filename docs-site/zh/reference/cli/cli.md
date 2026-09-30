---
title: coffer cli
description: "Check the command-line tools skills and MCP servers require"
---

# coffer cli

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

Check the command-line tools skills and MCP servers require

## cli list

```sh
coffer cli list [OPTIONS]
```

List every command a skill or MCP server requires, problems first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## cli show

```sh
coffer cli show [OPTIONS] COMMAND
```

Show one required command: where it is, its version and login state.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text | 必填 | The command, e.g. gh |
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
