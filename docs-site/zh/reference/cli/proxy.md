---
title: coffer proxy
description: "The local model proxy."
pageClass: cli-ref
---

# coffer proxy

The local model proxy.

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer proxy --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`proxy status`](#proxy-status) | The local model proxy's state. |
| [`proxy hint`](#proxy-hint) | The tail of an agent's proxy key. |
| [`proxy rotate`](#proxy-rotate) | Mint a new proxy key for an agent. |

## proxy status

The local model proxy's state.

<p class="cli-label">概要</p>

```sh
coffer proxy status [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## proxy hint

The tail of an agent's proxy key.

<p class="cli-label">概要</p>

```sh
coffer proxy hint [OPTIONS] AGENT_UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `AGENT_UID` <span class="cli-chip">参数</span> | text | 必填 | agent uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## proxy rotate

Mint a new proxy key for an agent.

<p class="cli-label">概要</p>

```sh
coffer proxy rotate [OPTIONS] AGENT_UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `AGENT_UID` <span class="cli-chip">参数</span> | text | 必填 | agent uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
