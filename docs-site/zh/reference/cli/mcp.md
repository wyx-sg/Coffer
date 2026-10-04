---
title: coffer mcp
description: "Check an MCP server"
pageClass: cli-ref
---

# coffer mcp

Check an MCP server

```sh
coffer mcp [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer mcp --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`mcp test`](#mcp-test) | Re-query a server's capabilities, then report whether it answers. |

## mcp test

Re-query a server's capabilities, then report whether it answers.

Exits 7 when the server does not answer. With ``--prompt``, a failure also prints the hand-off prompt the server's page offers for it: installing a launcher that is not found here, or finding why the server fails.

<p class="cli-label">概要</p>

```sh
coffer mcp test [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Server name |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | On a failure, also print the prompt to give your agent |
