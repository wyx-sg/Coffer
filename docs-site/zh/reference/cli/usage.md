---
title: coffer usage
description: "Model usage through Coffer's proxy, and subscription quota"
---

# coffer usage

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

Model usage through Coffer's proxy, and subscription quota

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--range` | 选项 | text | `today` | today \| 7d \| 30d \| month \| custom |
| `--from` | 选项 | text |  | First day of a custom range |
| `--to` | 选项 | text |  | Last day of a custom range, inclusive |
| `--by` | 选项 | text | `model` | model \| agent \| day |
| `--agent` | 选项 | text |  | Only requests this agent type sent (claude_code \| codex) |
| `--provider` | 选项 | text |  | Only requests this provider (by name) served |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--csv` | 选项 | 开关 |  | CSV output |

## usage requests

```sh
coffer usage requests [OPTIONS]
```

List recent metered requests, newest first.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--limit` | 选项 | integer (1-500) | `20` | Most requests to print |
| `--cursor` | 选项 | text |  | The next_cursor a read printed |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## usage quota

```sh
coffer usage quota [OPTIONS]
```

Show each subscription agent's official remaining quota.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--refresh` | 选项 | 开关 |  | Read Codex's windows now |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--prompt` | 选项 | 开关 |  | Print the prompt that has your agent set up the statusline wrapper |

## usage statusline

```sh
coffer usage statusline [OPTIONS] [COMMAND]...
```

Opt-in Claude Code statusLine wrapper: forward rate limits, then chain.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `COMMAND` | 参数 | text（可变个数） |  | The original statusLine command to run after forwarding |
