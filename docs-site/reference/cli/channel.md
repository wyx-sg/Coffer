---
title: coffer channel
description: "Manage messaging channels (Telegram, SeaTalk)"
---

# coffer channel

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer channel [OPTIONS] COMMAND [ARGS]...
```

Manage messaging channels (Telegram, SeaTalk)

## channel list

```sh
coffer channel list [OPTIONS]
```

List registered channels.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## channel show

```sh
coffer channel show [OPTIONS] NAME
```

Show a channel's configuration and status (runtime, binding, pairing, inbound).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--json` | option | flag |  | JSON output |

## channel add

```sh
coffer channel add [OPTIONS] NAME
```

Register a channel.

Its secrets are secret refs: store each secret first with `coffer secret set`, then pass the ref here.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |
| `--type` | option | text | required | telegram \| seatalk |
| `--bot-token-ref` | option | text |  | Secret ref of the Telegram bot token (store it with `coffer secret set`) |
| `--app-id` | option | text |  | SeaTalk App ID |
| `--app-secret-ref` | option | text |  | Secret ref of the SeaTalk app secret (store it with `coffer secret set`) |
| `--agent` | option | text | required | Name of the agent this channel drives by default (required) |
| `--agent-config` | option | text |  | Default agent config as JSON |
| `--runs-on` | option | text |  | machine_id of the machine that runs this channel (default: this one) |
| `--require-mention / --no-require-mention` | option | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | option | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | option | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | option | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | option | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | option | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` | option | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` | option | text (repeatable) |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--default-dir` | option | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--title` | option | text |  | Display title (≤80 chars) |
| `--description` | option | text |  |  |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## channel edit

```sh
coffer channel edit [OPTIONS] NAME
```

Change a channel's name, title, description, group gating, quiet windows, live status, completion ping, idle rollover, default directory or `/dir` directories.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--name` | option | text |  | New name |
| `--title` | option | text |  | Display title (≤80 chars); empty clears it |
| `--description` | option | text |  |  |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |
| `--require-mention / --no-require-mention` | option | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | option | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | option | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | option | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | option | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | option | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` | option | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` | option | text (repeatable) |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--no-dirs` | option | flag |  | Allow no directories for `/dir` (clears the list) |
| `--default-dir` | option | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--no-default-dir` | option | flag |  | Clear the default directory (the Coffer workspace applies) |

## channel rm

```sh
coffer channel rm [OPTIONS] NAME
```

Remove a channel and its pairings.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## channel enable

```sh
coffer channel enable [OPTIONS] NAME
```

Enable a channel (its adapter starts on the machine it is bound to).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## channel disable

```sh
coffer channel disable [OPTIONS] NAME
```

Disable a channel (its adapter stops).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## channel scope

```sh
coffer channel scope [OPTIONS] NAME
```

Show or set which agents a channel may drive (this machine only).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--agents` | option | text |  | Only these agents (a,b) |
| `--all` | option | flag |  | Every agent |
| `--none` | option | flag |  | No agent (dormant) |
| `--json` | option | flag |  | JSON output for scripts |

## channel pair

```sh
coffer channel pair [OPTIONS] NAME
```

Issue a pairing code; whoever sends it to the bot is added as a person.

Everyone paired is answered with the same rights; strangers are not. With ``--replace`` the sender takes over that person's place instead of joining.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |
| `--replace` | option | text |  | A paired person (id or name) whose place the new account takes |

## channel unpair

```sh
coffer channel unpair [OPTIONS] NAME PERSON
```

Remove a paired person: their chats stop being answered; everyone else stays.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |
| `PERSON` | argument | text | required | The paired person to remove (id or name) |

## channel bind

```sh
coffer channel bind [OPTIONS] NAME [MACHINE_ID]
```

Bind a channel to the machine that should run its adapter.

Takes effect without a restart: the binding is config, and both daemons reconcile config on their own loop. The machine LOSING the channel stops its adapter within a tick of seeing the change; the machine gaining it starts one within a tick of the converge round that brings the change over. Run it from the machine that currently holds the channel and the handover has no overlap at all.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |
| `MACHINE_ID` | argument | text |  | machine_id to bind to (default: this machine) |

## channel restart

```sh
coffer channel restart [OPTIONS] NAME
```

Stop the channel's adapter and start it again, reading its secret afresh.

Use it when a channel is stuck connecting, or to take a SeaTalk connection back from another process. Replacing a secret with `coffer secret set` already restarts the adapter on its own.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |

## channel notify

```sh
coffer channel notify [OPTIONS] NAME TEXT
```

Push a message to one of the channel's paired chats.

Without ``--chat`` it goes to the channel's first paired person's DM — its earliest pairing. Naming a chat the channel is not paired to is refused rather than delivered somewhere else.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Channel name |
| `TEXT` | argument | text | required | Message text |
| `--chat` | option | text |  | Paired chat id to push to (default: the first paired person's DM) |
