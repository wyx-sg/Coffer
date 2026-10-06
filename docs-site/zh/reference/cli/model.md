---
title: coffer model
description: "Ask a model endpoint which models it serves, or test it."
pageClass: cli-ref
---

# coffer model

Ask a model endpoint which models it serves, or test it.

```sh
coffer model [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer model --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`model list`](#model-list) | Ask an endpoint which models it serves. |
| [`model test`](#model-test) | Send one request to a model. |

## model list

Ask an endpoint which models it serves. Body: provider, base_url, secret_ref | secret_value.

<p class="cli-label">概要</p>

```sh
coffer model list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## model test

Send one request to a model. Body: provider, base_url, model, secret_ref | secret_value. Exits 7 when the answer says ok: false.

<p class="cli-label">概要</p>

```sh
coffer model test [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
