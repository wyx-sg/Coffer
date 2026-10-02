---
title: coffer channel
description: "Manage messaging channels (Telegram, SeaTalk)"
---

# coffer channel

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer channel [OPTIONS] COMMAND [ARGS]...
```

Manage messaging channels (Telegram, SeaTalk)

## channel list

```sh
coffer channel list [OPTIONS]
```

List registered channels.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## channel show

```sh
coffer channel show [OPTIONS] NAME
```

Show a channel's configuration and status (runtime, binding, pairing, inbound).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output |

## channel add

```sh
coffer channel add [OPTIONS] NAME
```

Register a channel.

Its secrets are secret refs: store each secret first with `coffer secret set`, then pass the ref here.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `--type` | 选项 | text | 必填 | telegram \| seatalk |
| `--bot-token-ref` | 选项 | text |  | Secret ref of the Telegram bot token (store it with `coffer secret set`) |
| `--app-id` | 选项 | text |  | SeaTalk App ID |
| `--app-secret-ref` | 选项 | text |  | Secret ref of the SeaTalk app secret (store it with `coffer secret set`) |
| `--agent` | 选项 | text | 必填 | Name of the agent this channel drives by default (required) |
| `--agent-config` | 选项 | text |  | Default agent config as JSON |
| `--runs-on` | 选项 | text |  | machine_id of the machine that runs this channel (default: this one) |
| `--require-mention / --no-require-mention` | 选项 | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | 选项 | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | 选项 | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | 选项 | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | 选项 | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | 选项 | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` | 选项 | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` | 选项 | text（可重复） |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--default-dir` | 选项 | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--title` | 选项 | text |  | Display title (≤80 chars) |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## channel edit

```sh
coffer channel edit [OPTIONS] NAME
```

Change a channel's name, title, description, group gating, quiet windows, live status, completion ping, idle rollover, default directory or `/dir` directories.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |
| `--require-mention / --no-require-mention` | 选项 | boolean |  | In groups, answer only when @mentioned or replied to (default: on) |
| `--ignore-other-mentions / --no-ignore-other-mentions` | 选项 | boolean |  | In groups, drop a message that @mentions anyone else (default: off) |
| `--wait-after-text` | 选项 | float (0-60) |  | Seconds to wait after a text message for more before answering (default: 1.5; 0 = none) |
| `--wait-after-forward` | 选项 | float (0-60) |  | Seconds to wait after a forwarded record or files with no text (default: 5; 0 = none) |
| `--show-steps / --hide-steps` | 选项 | boolean |  | List each step under the live status line while a turn runs (default: on) |
| `--notify-after` | 选项 | float (0-3600) |  | Ping the chat when a turn runs at least this many seconds (default: 90; 0 = never) |
| `--new-conversation-after-idle-hours` | 选项 | float (0-8760) |  | Open a new conversation when a chat was idle this many hours (default: 24; 0 = never) |
| `--dir` | 选项 | text（可重复） |  | An absolute directory `/dir` may switch into (repeat for several; replaces the list) |
| `--no-dirs` | 选项 | 开关 |  | Allow no directories for `/dir` (clears the list) |
| `--default-dir` | 选项 | text |  | The absolute directory new conversations start in (default: ~/.coffer/content/workspace) |
| `--no-default-dir` | 选项 | 开关 |  | Clear the default directory (the Coffer workspace applies) |

## channel rm

```sh
coffer channel rm [OPTIONS] NAME
```

Remove a channel and its pairings.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## channel enable

```sh
coffer channel enable [OPTIONS] NAME
```

Enable a channel (its adapter starts on the machine it is bound to).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## channel disable

```sh
coffer channel disable [OPTIONS] NAME
```

Disable a channel (its adapter stops).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## channel scope

```sh
coffer channel scope [OPTIONS] NAME
```

Show or set which agents a channel may drive (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## channel pair

```sh
coffer channel pair [OPTIONS] NAME
```

Issue a pairing code; send it to the bot from your own account.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |

## channel bind

```sh
coffer channel bind [OPTIONS] NAME [MACHINE_ID]
```

Bind a channel to the machine that should run its adapter.

Takes effect without a restart: the binding is config, and both daemons reconcile config on their own loop. The machine LOSING the channel stops its adapter within a tick of seeing the change; the machine gaining it starts one within a tick of the converge round that brings the change over. Run it from the machine that currently holds the channel and the handover has no overlap at all.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `MACHINE_ID` | 参数 | text |  | machine_id to bind to (default: this machine) |

## channel restart

```sh
coffer channel restart [OPTIONS] NAME
```

Stop the channel's adapter and start it again, reading its secret afresh.

Use it when a channel is stuck connecting, or to take a SeaTalk connection back from another process. Replacing a secret with `coffer secret set` already restarts the adapter on its own.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |

## channel notify

```sh
coffer channel notify [OPTIONS] NAME TEXT
```

Push a message to one of the channel's paired chats.

Without ``--chat`` it goes to the owner chat — the channel's earliest pairing, which is the owner's DM. Naming a chat the channel is not paired to is refused rather than delivered somewhere else.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Channel name |
| `TEXT` | 参数 | text | 必填 | Message text |
| `--chat` | 选项 | text |  | Paired chat id to push to (default: the owner's DM) |
