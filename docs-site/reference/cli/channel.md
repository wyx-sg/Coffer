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

This page matches what `coffer channel --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
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

<p class="cli-label">Synopsis</p>

```sh
coffer channel list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel show

One channel: its config, reach and state.

<p class="cli-label">Synopsis</p>

```sh
coffer channel show [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel update

Change a channel. Body: name, title, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer channel update [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel delete

Delete a channel.

<p class="cli-label">Synopsis</p>

```sh
coffer channel delete [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel enable

Switch a channel on.

<p class="cli-label">Synopsis</p>

```sh
coffer channel enable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel disable

Switch a channel off.

<p class="cli-label">Synopsis</p>

```sh
coffer channel disable [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel reach

Set the agents a channel reaches. Body: scope ({agents: [uid…]} or null).

<p class="cli-label">Synopsis</p>

```sh
coffer channel reach [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel add

Add a channel. Body: name, description, config.

<p class="cli-label">Synopsis</p>

```sh
coffer channel add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel status

Whether the channel is connected, and what waits.

<p class="cli-label">Synopsis</p>

```sh
coffer channel status [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel restart

Reconnect the channel.

<p class="cli-label">Synopsis</p>

```sh
coffer channel restart [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel notify

Send a message through the channel. Body: text, chat_id.

<p class="cli-label">Synopsis</p>

```sh
coffer channel notify [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel check-credentials

Check a platform's credentials before saving. Body: platform, bot_token | app_id + app_secret, channel_uid.

<p class="cli-label">Synopsis</p>

```sh
coffer channel check-credentials [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel pairing

Pair a person with a channel by a code they send the bot.

<p class="cli-label">Synopsis</p>

```sh
coffer channel pairing [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `start`, `cancel`.

## channel pairing start

Issue a pairing code a person sends to the bot.

<p class="cli-label">Synopsis</p>

```sh
coffer channel pairing start [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel pairing cancel

Withdraw the pairing code.

<p class="cli-label">Synopsis</p>

```sh
coffer channel pairing cancel [OPTIONS] UID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## channel person

The people paired with a channel.

<p class="cli-label">Synopsis</p>

```sh
coffer channel person [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `remove`.

## channel person remove

Remove a paired person.

<p class="cli-label">Synopsis</p>

```sh
coffer channel person remove [OPTIONS] UID SENDER_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `UID` <span class="cli-chip">argument</span> | text | required | The channel's name or uid |
| `SENDER_ID` <span class="cli-chip">argument</span> | text | required | sender id |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
