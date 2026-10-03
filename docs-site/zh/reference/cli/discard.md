---
title: coffer discard
description: "Remove one scanned item from the agent that holds it"
pageClass: cli-ref
---

# coffer discard

Remove one scanned item from the agent that holds it

```sh
coffer discard [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer discard --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`discard skill`](#discard-skill) | Delete an unmanaged skill folder from the agent's skill location (from disk). |
| [`discard mcp`](#discard-mcp) | Remove an MCP entry from the agent's own config file (a .bak is kept). |

## discard skill

Delete an unmanaged skill folder from the agent's skill location (from disk).

<p class="cli-label">概要</p>

```sh
coffer discard skill [OPTIONS] PATH
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">参数</span> | text | 必填 | The folder path the scan printed |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## discard mcp

Remove an MCP entry from the agent's own config file (a .bak is kept).

<p class="cli-label">概要</p>

```sh
coffer discard mcp [OPTIONS] AGENT:ENTRY
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `AGENT:ENTRY` <span class="cli-chip">参数</span> | text | 必填 | The ref the scan printed |
| `--source` <span class="cli-chip">选项</span> | text |  | Config-file key when the entry is in several files |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |
