---
title: coffer adopt
description: "Bring one scanned item under Coffer's management"
pageClass: cli-ref
---

# coffer adopt

Bring one scanned item under Coffer's management

```sh
coffer adopt [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer adopt --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`adopt skill`](#adopt-skill) | Move an unmanaged skill folder into Coffer's master store and link it back. |
| [`adopt mcp`](#adopt-mcp) | Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent. |

## adopt skill

Move an unmanaged skill folder into Coffer's master store and link it back.

<p class="cli-label">概要</p>

```sh
coffer adopt skill [OPTIONS] PATH
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | The folder path the scan printed |

## adopt mcp

Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent.

<p class="cli-label">概要</p>

```sh
coffer adopt mcp [OPTIONS] AGENT:ENTRY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `AGENT:ENTRY` <span class="cli-chip">参数</span> | text | 必填 | The ref the scan printed |
| `--name` <span class="cli-chip">选项</span> | text |  | Register the server under this name |
| `--source` <span class="cli-chip">选项</span> | text |  | Config-file key when the entry is in several files |
| `--secret` <span class="cli-chip">选项</span> | text（可重复） |  | KEY=SECRET_REF for a secret-like env/header key (repeatable) |
