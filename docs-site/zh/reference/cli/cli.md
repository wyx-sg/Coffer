---
title: coffer cli
description: "Read the command-line tools Coffer manages."
pageClass: cli-ref
---

# coffer cli

Read the command-line tools Coffer manages.

```sh
coffer cli [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer cli --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`cli list`](#cli-list) | List every command-line tool Coffer manages, problems first. |

## cli list

List every command-line tool Coffer manages, problems first.

The tools Coffer runs itself (git), the tools skills require, the launchers MCP servers start with, and the tools the developer added by hand: what each is for, who needs it, and whether it is ready, missing, outdated or logged out on this machine as of Coffer's last check. --json carries the full rows, including the prompt for an agent to install, update or log in to one that needs it.

<p class="cli-label">概要</p>

```sh
coffer cli list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
