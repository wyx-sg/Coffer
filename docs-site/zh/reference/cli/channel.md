---
title: coffer channel
description: "Messaging channels: status, pairing, people, notify, restart."
pageClass: cli-ref
---

# coffer channel

Messaging channels: status, pairing, people, notify, restart.

```sh
coffer channel [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer channel --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`channel list`](#channel-list) | Every channel. |
| [`channel show`](#channel-show) | One channel: its config, reach and state. |
| [`channel update`](#channel-update) | Change a channel. |
| [`channel delete`](#channel-delete) | Delete a channel. |
| [`channel enable`](#channel-enable) | Switch a channel on. |
| [`channel disable`](#channel-disable) | Switch a channel off. |
| [`channel reach`](#channel-reach) | Set the agents a channel reaches. |
| [`channel add`](#channel-add) | Add a channel. |
| [`channel status`](#channel-status) | Whether the channel is connected, and what waits. |
| [`channel restart`](#channel-restart) | Reconnect the channel. |
| [`channel notify`](#channel-notify) | Send a message through the channel. |
| [`channel check-credentials`](#channel-check-credentials) | Check a platform's credentials before saving. |
| [`channel pairing`](#channel-pairing) | Pair a person with a channel by a code they send the bot. |
| [`channel pairing start`](#channel-pairing-start) | Issue a pairing code a person sends to the bot. |
| [`channel pairing cancel`](#channel-pairing-cancel) | Withdraw the pairing code. |
| [`channel person`](#channel-person) | The people paired with a channel. |
| [`channel person remove`](#channel-person-remove) | Remove a paired person. |

## channel list

Every channel.

<p class="cli-label">概要</p>

```sh
coffer channel list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel show

One channel: its config, reach and state.

<p class="cli-label">概要</p>

```sh
coffer channel show [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel update

Change a channel. Body: name, title, description, config.

<p class="cli-label">概要</p>

```sh
coffer channel update [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel delete

Delete a channel.

<p class="cli-label">概要</p>

```sh
coffer channel delete [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel enable

Switch a channel on.

<p class="cli-label">概要</p>

```sh
coffer channel enable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel disable

Switch a channel off.

<p class="cli-label">概要</p>

```sh
coffer channel disable [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel reach

Set the agents a channel reaches. Body: scope ({agents: [uid…]} or null).

<p class="cli-label">概要</p>

```sh
coffer channel reach [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel add

Add a channel. Body: name, description, config.

<p class="cli-label">概要</p>

```sh
coffer channel add [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel status

Whether the channel is connected, and what waits.

<p class="cli-label">概要</p>

```sh
coffer channel status [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel restart

Reconnect the channel.

<p class="cli-label">概要</p>

```sh
coffer channel restart [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel notify

Send a message through the channel. Body: text, chat_id.

<p class="cli-label">概要</p>

```sh
coffer channel notify [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel check-credentials

Check a platform's credentials before saving. Body: platform, bot_token | app_id + app_secret, channel_uid.

<p class="cli-label">概要</p>

```sh
coffer channel check-credentials [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel pairing

Pair a person with a channel by a code they send the bot.

<p class="cli-label">概要</p>

```sh
coffer channel pairing [OPTIONS] COMMAND [ARGS]...
```

子命令：`start`, `cancel`。

## channel pairing start

Issue a pairing code a person sends to the bot.

<p class="cli-label">概要</p>

```sh
coffer channel pairing start [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--data, -d` <span class="cli-chip">选项</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">选项</span> | text（可重复） |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel pairing cancel

Withdraw the pairing code.

<p class="cli-label">概要</p>

```sh
coffer channel pairing cancel [OPTIONS] UID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel person

The people paired with a channel.

<p class="cli-label">概要</p>

```sh
coffer channel person [OPTIONS] COMMAND [ARGS]...
```

子命令：`remove`。

## channel person remove

Remove a paired person.

<p class="cli-label">概要</p>

```sh
coffer channel person remove [OPTIONS] UID SENDER_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">参数</span> | text | 必填 | The channel's name or uid |
| `SENDER_ID` <span class="cli-chip">参数</span> | text | 必填 | sender id |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
