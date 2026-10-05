---
title: coffer usage
description: "Model usage and cost."
pageClass: cli-ref
---

# coffer usage

Model usage and cost.

```sh
coffer usage [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer usage --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`usage summary`](#usage-summary) | Model usage and cost over a range, grouped. |

## usage summary

Model usage and cost over a range, grouped.

<p class="cli-label">概要</p>

```sh
coffer usage summary [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--range` <span class="cli-chip">选项</span> | text |  | 24h, 7d, 30d… |
| `--from` <span class="cli-chip">选项</span> | text |  |  |
| `--to` <span class="cli-chip">选项</span> | text |  |  |
| `--group-by` <span class="cli-chip">选项</span> | text |  | model, agent, connection, day |
| `--agent-type` <span class="cli-chip">选项</span> | text |  |  |
| `--connection-uid` <span class="cli-chip">选项</span> | text |  |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
