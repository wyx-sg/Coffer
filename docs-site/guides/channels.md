---
title: Channels
description: Connect a Telegram bot or SeaTalk app to Coffer, pair it to your own account, and drive Claude Code or Codex from the IM app you already use.
---

# Channels

A **channel** connects one Telegram bot or one SeaTalk app to Coffer, so you can talk to your agents from your phone and receive notifications Coffer pushes. This page covers what every channel shares — pairing, the default agent and scope, the machine a channel runs on, commands, media and security. For platform setup, follow [Telegram](/guides/channels-telegram) or [SeaTalk](/guides/channels-seatalk).

## What a channel is

A channel is a registered resource of kind `channel`. It holds:

- the platform type, `telegram` or `seatalk`, and that platform's settings;
- **references** to its secrets in Coffer's [credential store](/guides/credentials), never the secrets themselves;
- a **default agent** — the agent a new conversation on this channel starts on;
- `runs_on` — the one machine whose daemon runs the channel's adapter.

A message from you becomes a turn in an ordinary Coffer conversation, and the agent's reply goes back to the IM chat. The conversation is the same one the web [Chat](/guides/chat) page lists, with a **via** badge naming the channel, so you can start a task on your phone and watch or continue it in the browser.

One bot drives every managed agent. You switch between Claude Code and Codex from the chat with `/agent`, and different threads of one group can run different agents at the same time.

::: info Coffer-hosted channels only
Coffer manages the channels it hosts. An agent's own official integration — Claude Code's Telegram plugin, a vendor's Slack app, an agent-native gateway — runs on its own and is not managed or proxied by Coffer.
:::

## Register a channel

Both ways store the secret first and register the channel with a reference to it.

::: code-group

```sh [CLI]
# Store the secret (read from stdin, so it stays out of your shell history)
coffer credentials set channel/tg/bot-token

# Register the channel; --agent is the agent's name as the Agents page shows it
coffer channel register my-telegram --type telegram \
  --bot-token-ref channel/tg/bot-token --agent claude-code
```

```text [Web UI]
Channels → Add channel
  Type:           Telegram | SeaTalk
  Name:           my-telegram
  Bot token:      (or App ID + App secret for SeaTalk)
  Default agent:  claude-code
```

:::

In the web UI, **Add channel** writes the secret to the credential store and registers the channel in one step. A name is letters, digits, dash and underscore, at most 64 characters.

A registration whose credential reference does not resolve is rejected and nothing is saved. So is one naming a default agent that is not registered in this vault.

A new channel is bound to the machine you register it from and may drive every registered agent. Its adapter starts as soon as it is saved.

## Pair your account

Pairing makes you the channel's owner. Until a channel is paired, it answers nobody.

1. Issue a code: on the channel's page, **Pairing → Generate pairing code**, or

   ```sh
   coffer channel pair my-telegram
   ```

   ```text
   pairing code: K7QM3XPA
   expires at:   2026-09-24T15:04:05Z
   pair link:    https://t.me/my_coffer_bot?start=K7QM3XPA
   Send this code to the bot from the account that should own the channel.
   ```

2. From your own account, send the eight characters to the bot as a message. On Telegram you can open the pair link instead (**Open the pairing link**), which sends the code for you.
3. The bot confirms. You are now the channel's sole owner.

A code is eight characters from an alphabet with no `0`, `O`, `1` or `I`. It works once, expires after one hour, and is invalidated after 10 wrong guesses. Codes are held in the daemon's memory only, so restarting the daemon drops an unused code; generate another.

Pairing again from a different account replaces the owner. The previous owner's direct chat and group pairings are removed.

## Talk to an agent

Send the bot a message. The first message opens a conversation on the channel's default agent, in the Coffer-managed workspace `~/.coffer/workspace`, and every later message continues it.

- A 👀 reaction (Telegram) or a typing indicator (SeaTalk) says the message was received.
- The reply grows in place while the agent works, with one progress line per tool call, such as `⏳ Bash · list the desktop` and `✅ Read · wedding.json`.
- A turn that fails, is stopped, or hits the tool-iteration limit ends with a one-line summary: the outcome, tool count, duration and tokens. A turn that succeeds sends no summary; the reply is the signal.

Messages you send while a turn is running wait in the conversation's queue and run in order — the same queue the Chat page shows. The channel accepts up to 10 waiting messages; past that it tells you the channel is busy and drops the message.

Each turn tells the agent it is on a chat channel: keep replies concise, and it cannot click dialogs on your computer. Each turn also opens with a `[Message origin]` block naming the platform, the chat, the thread and the sender, so the agent can answer "which group is this?" and aim a platform tool call at the right chat.

## Commands

Commands work from any paired chat — a direct chat, a group or a thread. `/help` lists them and the bot registers the same list as its command menu.

| Command | What it does |
| --- | --- |
| `/new` | Start a fresh conversation with this thread's current agent. The old one stays in history. |
| `/agent [key]` | Without an argument, show the current agent and the ones this channel may drive, as buttons where the platform has them. With a key, switch to that agent. Switching opens a fresh conversation and sticks for this thread. |
| `/model [name]` | Without an argument, show the current model and a paged picker of the agent's model catalogue. With a name, use that model from the next turn in the same conversation. |
| `/effort [level]` | Show or switch the reasoning effort for the model the conversation is on, from the next turn. A model with no levels says so. |
| `/stop` | Interrupt the running turn and pause the queue. |
| `/status` | Show the active conversation, agent and turn state, including how many messages are waiting. |
| `/save [collection]` | Save the document you just sent into a [knowledge](/guides/knowledge) collection. Without a collection, it asks which. |
| `/help` | List the commands. |

`/new` and `/stop` take effect even while a turn is running. `/start`, which a Telegram start link sends, answers with the help text.

Notes on the switches:

- `/agent` is structural: an existing conversation's agent cannot change, so switching opens a new one. `/model` and `/effort` are parametric: they apply to the next turn of the same conversation.
- `/model` validates nothing. The name is passed to the agent's CLI as is, so you can use a model the picker does not list; a name the agent cannot run comes back as the CLI's own error on the next turn.
- There is no command to clear a model or effort override. `/new` starts a conversation with no overrides.
- `/save` needs the Knowledge feature switched on. See [Experimental features](/guides/experimental-features).

In a group, the answers to `/agent`, `/model`, `/effort`, `/status` and `/help` are delivered privately to you where the platform supports it; `/new`, `/stop` and `/save` stay visible to the room.

### Selection cards

On a platform with buttons, `/agent`, `/model`, `/effort` and a `/save` with no collection answer with a selection card. A card carries at most six buttons; a longer list is paged, four choices at a time with **← Prev** and **Next →**. Paging changes nothing — only tapping a choice does. After a tap, the card is rewritten in place so the tick moves to your new choice.

A button tap is checked exactly like a message: only the owner's taps count. If the platform refuses a card, the command answers in plain text instead.

## Default agent and scope

Two settings decide which agent answers.

**The default agent** is the agent a new conversation starts on. Set it when you register the channel; change it with **Edit** on the channel's page.

**The scope** is the channel's reach — the list of agents it **may drive**. For every other resource kind, scope names the agents a resource is delivered *to*; a channel is used by no agent, so its scope is read the other way round. Set it with the **Reach** button on the channel's row or page, or:

```sh
coffer scope set channel my-telegram --agents claude-code   # may drive only Claude Code
coffer scope clear channel my-telegram                       # may drive every agent
coffer scope set channel my-telegram --no-agents             # dormant: drives nothing
```

- An unrestricted scope means every registered agent.
- A restricted scope narrows `/agent` everywhere: the list, the card, and the check on a key you type or tap.
- The default agent must always be inside the scope. Coffer refuses a scope that excludes the current default agent, and a default agent outside the current scope, naming both by label, so you either widen the scope or change the default first.
- An empty scope makes the channel **dormant**: its adapter does not start. A dormant channel can still be edited, for example to fix a wrong token.
- Narrowing the scope drops a thread's sticky `/agent` choice that is no longer allowed; the next conversation uses the default agent.

Like every reach setting, scope and the enabled switch are set per machine and are not synced.

::: warning A channel with nowhere to route does not start
A channel with no default agent, a default agent outside its scope, or a default agent not registered on this machine does not start, and its status says why. Coffer never substitutes another agent.
:::

## The machine a channel runs on

A bot tolerates exactly one consumer: two machines polling one Telegram bot, or holding one SeaTalk app's connection, fight over its messages. So each channel names the one machine that runs it, in `runs_on`. Unlike reach, `runs_on` is part of the channel's configuration and travels with it through [vault sync](/guides/vault-sync), so every machine reads the same answer.

- A channel registered from any Coffer surface is bound to the registering machine.
- Only the named machine starts the adapter. A channel bound to another machine is shown as running elsewhere, not as stopped.
- A channel with no binding, or bound to a machine the registry does not know, runs nowhere and says so on its page.

To move a channel, change **Runs on** on its page, or:

```sh
coffer channel bind my-telegram              # bind to this machine
coffer channel bind my-telegram <machine_id> # bind to another machine
```

Rebinding needs no restart. The machine losing the channel stops its adapter within a reconcile tick; the machine gaining it starts one after the next sync round brings the change over. Rebind from the machine that currently runs the channel for a clean handover. Binding a channel to the machine you are on while another machine still runs it can leave both answering until that machine's next sync round.

Your pairing travels with the channel, so moving it does not make you pair again.

## Groups and threads

Add the bot to a group to use it there.

- The bot acts only on a message addressed to it — an @mention, or a reply to the bot. Other group messages are ignored.
- Only the owner can drive it. An addressed message from anyone else gets a short "not authorized" reply and starts no turn.
- In the group's main chat, the answer goes into a thread rooted at your message, never into the main chat. Inside a thread, the bot replies in that thread.
- Each thread is its own conversation with its own agent, history and queue, so threads run concurrently.
- A group answer is a reply to the message that asked, and on SeaTalk it @mentions you.
- When you quote a message, the quoted sender and text are folded into the turn as `> sender: …` lines above your text.
- A forwarded chat record is flattened into a `[Forwarded chat record]` block.

Two channel settings tune when the bot answers in a group: `require_mention` (on by default) and `ignore_other_mentions` (off by default; when on, a message that also @mentions a person is ignored). Neither has a control in the web UI or the CLI; set them in the channel's configuration through `PATCH /api/v1/resources/{uid}`. They change when the bot answers, never who may drive it.

If the bot is removed from a group, that group's sessions stop. If a SeaTalk group becomes an external group, the bot posts one warning in it.

## Media

Send photos, files, voice messages and other media as you would to a person. Each attachment is downloaded to `~/.coffer/channel-media` and handed to the agent in the form it can use:

| You send | The agent receives |
| --- | --- |
| A photo or sticker | Claude Code sees the image. Codex gets the file path. |
| A PDF, office document, epub or rtf | The extracted text, in a `[Document: <name>]` block. If extraction is unavailable, the file path. |
| A voice message or audio | A transcript, when **Speech to text** is on under **Settings → Coffer's model**. Otherwise the audio file. |
| Any other file | The file path. |
| A location, a contact card | Nothing to download: the bot asks for text, a photo or a file. |

A file larger than the platform lets a bot download is not fetched; the turn text notes it, so the reply acknowledges it. Attachments are stored as references, so a later turn in the same conversation can still reach them. Files in `~/.coffer/channel-media` are pruned 30 days after they were last modified.

::: warning Voice transcription sends audio off your machine
Transcription sends the audio to the transcription provider you configured. It is off until you choose both a transcription provider and a model. A transcription failure never fails the turn; the agent gets the audio file instead.
:::

### Sending files back

The agent sends you a file by writing a line of its own:

```text
MEDIA:/Users/you/reports/q3-chart.png | Q3 revenue by region
```

The line must start with `MEDIA:` followed by an absolute path, optionally with `| caption`. The channel uploads the file into the same chat and thread the turn came from — an image as a photo, anything else as a document — and removes the line from the reply. A path that is missing, relative or over 50 MB is left as text. Ordinary Markdown such as `![chart](chart.png)` is never uploaded. The channel note tells the agent about this syntax, so you can simply ask for the file.

## Notifications

Coffer can push a message to the paired owner with no inbound message:

```sh
coffer channel notify my-telegram "build finished"
coffer channel notify my-telegram "deploy done" --chat -1001234567890
```

Without `--chat` the message goes to the owner's direct chat. `--chat` names another paired chat, such as a group; a chat the channel is not paired to is refused. On the channel's page, **Test delivery** does the same. Notifying a channel with no paired owner fails and sends nothing. The REST equivalent is `POST /api/v1/channels/{uid}/notify`.

## Manage channels

The **Channels** page lists every channel with **Name**, **Type**, **Default agent**, **Health** (Running or Stopped), **Runs on**, **Paired** and its reach. A channel's page shows:

- **Status** — the adapter, the paired peer and its chat ID, when it was paired, and the active conversation.
- **Runs on** — the machine binding, with the handover notes above.
- **Pairing** — generate a code.
- **SeaTalk connection** — for SeaTalk, the websocket connection state and its last error.
- **Test delivery** — send a one-off message to the owner.
- **Edit** — change the default agent, the SeaTalk App ID, or rotate a secret. A blank secret field keeps the current value; a new one is written under the reference the channel already uses, so rotating a secret changes neither pairing nor binding.

From the CLI:

```sh
coffer channel list
coffer channel status my-telegram
coffer resource disable channel my-telegram   # stop the adapter
coffer resource enable channel my-telegram    # start it again
coffer resource delete channel my-telegram    # stop it and remove the pairing
printf %s "$NEW_TOKEN" | coffer credentials set channel/tg/bot-token   # rotate
```

```text
channel:  my-telegram (telegram)
enabled:  True    running: True
runs on:  3f9c… (this machine)
pairing:  no pending code
peer:     Ada (chat 123456789)
conv:     01J8Z…
```

`coffer channel status` also prints a `warning:` line for a setting on the platform that defeats the channel's configuration, such as Telegram privacy mode.

## Security

Owner pairing is the security boundary for everything a channel can do.

- **Only the paired owner drives agents.** Coffer checks both the chat and the sender's platform identity — Telegram's user id, SeaTalk's employee code — so another member of a paired group cannot drive a turn.
- **Strangers get silence.** A message from anyone who is not the owner produces no reply and no turn in a direct chat, so the bot does not reveal that it is running. In a group, an addressed message from a non-owner gets a short refusal.
- **A tap is checked like a message.** A button on a selection card never pairs and never switches anything for a non-owner.
- **Agents run with full permissions.** There is no approval step for tool calls. Anyone who can pair the bot can make an agent act on your machine, so treat a pairing code like a password and generate it only when you are about to use it.
- **Secrets stay in the vault.** The channel configuration holds only credential references; Coffer refuses a value that looks like a raw secret in a reference field.
- **Nothing is exposed to the network.** Telegram is polled and SeaTalk is an outbound websocket; neither opens a port or needs a public URL.

Pairing codes issued and claimed are written to the audit log, together with the channel's lifecycle changes. Messages, notifications and turns are not; the conversation is their record.

## How it works

The channel layer meets the agents only at the turn platform's seams — conversation creation and the turn event stream — so a new channel type is one adapter and touches no agent code, and a new agent is reachable from every channel with no channel change. Each adapter declares its capabilities (live text, edits, buttons, reactions, media), and the core chooses how to render a reply from those declarations, never from the platform's name. See [Chat and turns](/architecture/chat).

## Related

- [Telegram setup](/guides/channels-telegram)
- [SeaTalk setup](/guides/channels-seatalk)
- [Chat](/guides/chat) — the same conversations in the browser.
- [Credentials](/guides/credentials) — where channel secrets live.
- [Vault sync](/guides/vault-sync) — how a channel's binding and pairing travel between machines.
- [Security model](/architecture/security)
- [Spec: channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md)
- [Channel Adapter Framework](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md), [Channel Media](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-media.md)
