---
title: coffer channel
description: "Manage messaging channels (Telegram, SeaTalk)"
pageClass: cli-ref
---

# coffer channel

Manage messaging channels (Telegram, SeaTalk)

```sh
coffer channel [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer channel --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`channel list`](#channel-list) | List registered channels. |
| [`channel show`](#channel-show) | Show a channel's configuration and status (runtime, binding, pairing, inbound). |
| [`channel add`](#channel-add) | Register a channel. |
| [`channel edit`](#channel-edit) | Change a channel's name, title, description, group gating, quiet windows, live status, completion ping, idle rollover, default directory or `/dir` directories. |
| [`channel rm`](#channel-rm) | Remove a channel and its pairings. |
| [`channel enable`](#channel-enable) | Enable a channel (its adapter starts on the machine it is bound to). |
| [`channel disable`](#channel-disable) | Disable a channel (its adapter stops). |
| [`channel scope`](#channel-scope) | Show or set which agents a channel may drive (this machine only). |
| [`channel pair`](#channel-pair) | Issue a pairing code; whoever sends it to the bot is added as a person. |
| [`channel unpair`](#channel-unpair) | Remove a paired person: their chats stop being answered; everyone else stays. |
| [`channel bind`](#channel-bind) | Bind a channel to the machine that should run its adapter. |
| [`channel restart`](#channel-restart) | Stop the channel's adapter and start it again, reading its secret afresh. |
| [`channel notify`](#channel-notify) | Push a message to one of the channel's paired chats. |

## channel list

List registered channels.

<p class="cli-label">Synopsis</p>

```sh
coffer channel list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## channel show

Show a channel's configuration and status (runtime, binding, pairing, inbound).

<p class="cli-label">Synopsis</p>

```sh
coffer channel show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output |

## channel add

Register a channel.

Its secrets are secret refs: store each secret first with `coffer secret set`, then pass the ref here.

<p class="cli-label">Synopsis</p>

```sh
coffer channel add [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |
| `--type` <span class="cli-chip">option</span> | text | required | telegram \| seatalk |
| `--bot-token-ref` <span class="cli-chip">option</span> | text |  | Secret ref of the Telegram bot token (store it with `coffer secret set`) |
| `--app-id` <span class="cli-chip">option</span> | text |  | SeaTalk App ID |
| `--app-secret-ref` <span class="cli-chip">option</span> | text |  | Secret ref of the SeaTalk app secret (store it with `coffer secret set`) |
| `--agent` <span class="cli-chip">option</span> | text | required | Name of the agent this channel drives by default (required) |
| `--agent-config` <span class="cli-chip">option</span> | text |  | Default agent config as JSON |
| `--runs-on` <span class="cli-chip">option</span> | text |  | machine_id of the machine that runs this channel (default: this one) |
| `--require-mention / --no-require-mention` <span class="cli-chip">option</span> | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` <span class="cli-chip">option</span> | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` <span class="cli-chip">option</span> | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` <span class="cli-chip">option</span> | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` <span class="cli-chip">option</span> | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` <span class="cli-chip">option</span> | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` <span class="cli-chip">option</span> | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` <span class="cli-chip">option</span> | text (repeatable) |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--default-dir` <span class="cli-chip">option</span> | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--title` <span class="cli-chip">option</span> | text |  | Display title (≤80 chars) |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## channel edit

Change a channel's name, title, description, group gating, quiet windows, live status, completion ping, idle rollover, default directory or `/dir` directories.

<p class="cli-label">Synopsis</p>

```sh
coffer channel edit [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--name` <span class="cli-chip">option</span> | text |  | New name |
| `--title` <span class="cli-chip">option</span> | text |  | Display title (≤80 chars); empty clears it |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |
| `--require-mention / --no-require-mention` <span class="cli-chip">option</span> | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` <span class="cli-chip">option</span> | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` <span class="cli-chip">option</span> | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` <span class="cli-chip">option</span> | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` <span class="cli-chip">option</span> | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` <span class="cli-chip">option</span> | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` <span class="cli-chip">option</span> | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` <span class="cli-chip">option</span> | text (repeatable) |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--no-dirs` <span class="cli-chip">option</span> | flag |  | Allow no directories for `/dir` (clears the list) |
| `--default-dir` <span class="cli-chip">option</span> | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--no-default-dir` <span class="cli-chip">option</span> | flag |  | Clear the default directory (the Coffer workspace applies) |

## channel rm

Remove a channel and its pairings.

<p class="cli-label">Synopsis</p>

```sh
coffer channel rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## channel enable

Enable a channel (its adapter starts on the machine it is bound to).

<p class="cli-label">Synopsis</p>

```sh
coffer channel enable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## channel disable

Disable a channel (its adapter stops).

<p class="cli-label">Synopsis</p>

```sh
coffer channel disable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## channel scope

Show or set which agents a channel may drive (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer channel scope [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Every agent |
| `--none` <span class="cli-chip">option</span> | flag |  | No agent (dormant) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## channel pair

Issue a pairing code; whoever sends it to the bot is added as a person.

Everyone paired is answered with the same rights; strangers are not. With ``--replace`` the sender takes over that person's place instead of joining.

<p class="cli-label">Synopsis</p>

```sh
coffer channel pair [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |
| `--replace` <span class="cli-chip">option</span> | text |  | A paired person (id or name) whose place the new account takes |

## channel unpair

Remove a paired person: their chats stop being answered; everyone else stays.

<p class="cli-label">Synopsis</p>

```sh
coffer channel unpair [OPTIONS] NAME PERSON
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |
| `PERSON` <span class="cli-chip">argument</span> | text | required | The paired person to remove (id or name) |

## channel bind

Bind a channel to the machine that should run its adapter.

Takes effect without a restart: the binding is config, and both daemons reconcile config on their own loop. The machine LOSING the channel stops its adapter within a tick of seeing the change; the machine gaining it starts one within a tick of the converge round that brings the change over. Run it from the machine that currently holds the channel and the handover has no overlap at all.

<p class="cli-label">Synopsis</p>

```sh
coffer channel bind [OPTIONS] NAME [MACHINE_ID]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |
| `MACHINE_ID` <span class="cli-chip">argument</span> | text |  | machine_id to bind to (default: this machine) |

## channel restart

Stop the channel's adapter and start it again, reading its secret afresh.

Use it when a channel is stuck connecting, or to take a SeaTalk connection back from another process. Replacing a secret with `coffer secret set` already restarts the adapter on its own.

<p class="cli-label">Synopsis</p>

```sh
coffer channel restart [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |

## channel notify

Push a message to one of the channel's paired chats.

Without ``--chat`` it goes to the channel's first paired person's DM — its earliest pairing. Naming a chat the channel is not paired to is refused rather than delivered somewhere else.

<p class="cli-label">Synopsis</p>

```sh
coffer channel notify [OPTIONS] NAME TEXT
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Channel name |
| `TEXT` <span class="cli-chip">argument</span> | text | required | Message text |
| `--chat` <span class="cli-chip">option</span> | text |  | Paired chat id to push to (default: the first paired person's DM) |
