---
title: coffer proxy
description: "Inspect the local model proxy and its per-agent tokens"
pageClass: cli-ref
---

# coffer proxy

Inspect the local model proxy and its per-agent tokens

```sh
coffer proxy [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer proxy --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`proxy token`](#proxy-token) | Print an agent's local proxy token (what its key helper runs). |
| [`proxy rotate`](#proxy-rotate) | Replace an agent's local proxy token; the old one stops working at once. |
| [`proxy status`](#proxy-status) | Show whether the model proxy is running, where, and how often it restarted. |

## proxy token

Print an agent's local proxy token (what its key helper runs).

The token unlocks only this machine's loopback model proxy; it is never a provider key. Exits 4 with nothing on stdout for an agent this machine does not have, so a stale helper fails instead of printing a token.

<p class="cli-label">概要</p>

```sh
coffer proxy token [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--agent-uid` <span class="cli-chip">选项</span> | text | 必填 | The agent whose token to print |

## proxy rotate

Replace an agent's local proxy token; the old one stops working at once.

<p class="cli-label">概要</p>

```sh
coffer proxy rotate [OPTIONS] REF
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">参数</span> | text | 必填 | Agent name or uid |

## proxy status

Show whether the model proxy is running, where, and how often it restarted.

<p class="cli-label">概要</p>

```sh
coffer proxy status [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Machine-readable output |
