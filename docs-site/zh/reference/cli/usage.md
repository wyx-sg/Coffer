---
title: coffer usage
description: "Model usage through Coffer's proxy"
pageClass: cli-ref
---

# coffer usage

Model usage through Coffer's proxy

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer usage --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--range` <span class="cli-chip">选项</span> | text | `today` | today \| 7d \| 30d \| month \| custom |
| `--from` <span class="cli-chip">选项</span> | text |  | First day of a custom range |
| `--to` <span class="cli-chip">选项</span> | text |  | Last day of a custom range, inclusive |
| `--by` <span class="cli-chip">选项</span> | text | `model` | model \| agent \| day |
| `--agent` <span class="cli-chip">选项</span> | text |  | Only requests this agent type sent (claude_code \| codex) |
| `--provider` <span class="cli-chip">选项</span> | text |  | Only requests this provider (by name) served |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
| `--csv` <span class="cli-chip">选项</span> | 开关 |  | CSV output |

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`usage requests`](#usage-requests) | List recent metered requests, newest first. |

## usage requests

List recent metered requests, newest first.

<p class="cli-label">概要</p>

```sh
coffer usage requests [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--limit` <span class="cli-chip">选项</span> | integer (1-500) | `20` | Most requests to print |
| `--cursor` <span class="cli-chip">选项</span> | text |  | The next_cursor a read printed |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
