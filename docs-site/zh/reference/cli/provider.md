---
title: coffer provider
description: "Model providers: connections, prices, switching agents' models."
pageClass: cli-ref
---

# coffer provider

Model providers: connections, prices, switching agents' models.

```sh
coffer provider [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer provider --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`provider list`](#provider-list) | Model provider connections. |
| [`provider show`](#provider-show) | One connection. |
| [`provider add`](#provider-add) | Add a connection. |
| [`provider update`](#provider-update) | Change a connection. |
| [`provider health`](#provider-health) | Each connection's last health verdict: reachable, key_rejected or unreachable. |
| [`provider check`](#provider-check) | List a connection's models now and keep its health verdict. |
| [`provider delete-preview`](#provider-delete-preview) | What deleting a connection would change. |
| [`provider delete`](#provider-delete) | Delete a connection. |
| [`provider prices`](#provider-prices) | Prices of the given models on this connection. |
| [`provider transcribe-default`](#provider-transcribe-default) | Make this connection the transcription default. |
| [`provider detect-local`](#provider-detect-local) | Find a local model runtime (Ollama, LM Studio). |
| [`provider price-list`](#provider-price-list) | The bundled model price list. |
| [`provider price-list show`](#provider-price-list-show) | The bundled model price list and its age. |
| [`provider price-list refresh`](#provider-price-list-refresh) | Refresh the price list. |
| [`provider switch`](#provider-switch) | Switch an agent type's model to a connection: preview, then apply. |
| [`provider switch preview`](#provider-switch-preview) | What switching an agent type's model would write. |
| [`provider switch apply`](#provider-switch-apply) | Switch an agent type's model. |

## provider list

Model provider connections.

<p class="cli-label">概要</p>

```sh
coffer provider list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider show

One connection.

<p class="cli-label">概要</p>

```sh
coffer provider show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider add

Add a connection. Body: name, protocol, base_url, secret_ref | secret_value, models, description, local_runtime.

<p class="cli-label">概要</p>

```sh
coffer provider add [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider update

Change a connection. Body: base_url, protocol, secret_ref | secret_value, models, description.

<p class="cli-label">概要</p>

```sh
coffer provider update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider health

Each connection's last health verdict: reachable, key_rejected or unreachable.

<p class="cli-label">概要</p>

```sh
coffer provider health [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider check

List a connection's models now and keep its health verdict.

<p class="cli-label">概要</p>

```sh
coffer provider check [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider delete-preview

What deleting a connection would change.

<p class="cli-label">概要</p>

```sh
coffer provider delete-preview [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider delete

Delete a connection.

<p class="cli-label">概要</p>

```sh
coffer provider delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider prices

Prices of the given models on this connection. Body: models.

<p class="cli-label">概要</p>

```sh
coffer provider prices [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider transcribe-default

Make this connection the transcription default.

<p class="cli-label">概要</p>

```sh
coffer provider transcribe-default [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The provider's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider detect-local

Find a local model runtime (Ollama, LM Studio). Body: base_url.

<p class="cli-label">概要</p>

```sh
coffer provider detect-local [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider price-list

The bundled model price list.

<p class="cli-label">概要</p>

```sh
coffer provider price-list [OPTIONS] COMMAND [ARGS]...
```

子命令：`show`, `refresh`。

## provider price-list show

The bundled model price list and its age.

<p class="cli-label">概要</p>

```sh
coffer provider price-list show [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider price-list refresh

Refresh the price list. Body: refresh (--set refresh=true).

<p class="cli-label">概要</p>

```sh
coffer provider price-list refresh [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider switch

Switch an agent type's model to a connection: preview, then apply.

<p class="cli-label">概要</p>

```sh
coffer provider switch [OPTIONS] COMMAND [ARGS]...
```

子命令：`preview`, `apply`。

## provider switch preview

What switching an agent type's model would write. Body: agent_type, connection_uid, model, tier_models, native_model, clear_native_model.

<p class="cli-label">概要</p>

```sh
coffer provider switch preview [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## provider switch apply

Switch an agent type's model. Body as for preview, plus seen.

<p class="cli-label">概要</p>

```sh
coffer provider switch apply [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
