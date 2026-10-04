---
title: coffer secret
description: "Manage encrypted secrets."
pageClass: cli-ref
---

# coffer secret

Manage encrypted secrets.

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer secret --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`secret set`](#secret-set) | Store a secret in the encrypted secret store (via the daemon). |
| [`secret list`](#secret-list) | List every stored secret and every ref a resource cites. |

## secret set

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

<p class="cli-label">概要</p>

```sh
coffer secret set [OPTIONS] REF
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">参数</span> | text | 必填 | Secret reference key |
| `--value` <span class="cli-chip">选项</span> | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |

## secret list

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

<p class="cli-label">概要</p>

```sh
coffer secret list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
