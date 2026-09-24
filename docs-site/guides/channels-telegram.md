---
title: Telegram
description: Set up a Telegram channel for Coffer — create a bot with BotFather, store its token, register the channel, pair your account and chat with your agents.
---

# Telegram

This guide sets up a Telegram channel from scratch: create a bot with BotFather, store its token in Coffer, register the channel, pair your account, and get your first agent reply. It then covers media, groups, limits and troubleshooting. For what every channel shares — commands, scope, machine binding, security — see [Channels](/guides/channels).

Telegram is the channel you can set up entirely on your own. It needs no public URL, no tunnel, no vendor SDK and no organisation approval: Coffer long-polls the Telegram Bot API at `api.telegram.org` over an outbound connection.

## Prerequisites

- A running daemon and at least one registered agent. See [Quickstart](/start/quickstart).
- The Telegram app, signed in to the account you want to own the channel.

## 1. Create a bot

1. In Telegram, open a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, then choose a display name and a username ending in `bot` (for example `my_coffer_bot`).
3. BotFather replies with the bot's token, which looks like `123456789:AAH…`. Copy it.

::: danger
The token is full control of the bot. Keep it out of chat logs, screenshots and shell history. If it leaks, send `/revoke` to BotFather and rotate it in Coffer (see [Rotate the token](#rotate-the-token)).
:::

You do not need to set a description or a command list: Coffer registers the bot's command menu on start and fills in an empty description. A description you set yourself in BotFather is left as it is.

## 2. Register the channel

::: code-group

```sh [CLI]
# Paste the token at the prompt; it is read from stdin, not your shell history
coffer credentials set channel/tg/bot-token

coffer channel register my-telegram --type telegram \
  --bot-token-ref channel/tg/bot-token \
  --agent claude-code
```

```text [Web UI]
Channels → Add channel
  Type:           Telegram
  Name:           my-telegram
  Bot token:      123456789:AAH…
  Default agent:  claude-code
→ Create
```

:::

`--agent` is the name of a registered agent, as the **Agents** page lists it. The channel is bound to the machine you register it from and starts polling immediately. A token reference that does not resolve is rejected and nothing is saved.

Check that it is running:

```sh
coffer channel status my-telegram
```

```text
channel:  my-telegram (telegram)
enabled:  True    running: True
runs on:  3f9c… (this machine)
pairing:  no pending code
peer:     not paired
```

## 3. Pair your account

1. Issue a code, on the channel's page with **Pairing → Generate pairing code**, or:

   ```sh
   coffer channel pair my-telegram
   ```

   ```text
   pairing code: K7QM3XPA
   expires at:   2026-09-24T15:04:05Z
   pair link:    https://t.me/my_coffer_bot?start=K7QM3XPA
   Send this code to the bot from the account that should own the channel.
   ```

2. Open the pair link on the phone signed in to your account (**Open the pairing link** on the web page) and tap **Start**. Or open the bot and send `K7QM3XPA` as a message.
3. The bot confirms the pairing. You are the owner.

The code is single-use, expires after an hour, and is invalidated after 10 wrong guesses. Until you pair, the bot does not answer anyone.

## 4. Send your first message

Send the bot a message, for example `list the files in my home directory`. You should see:

1. a 👀 reaction on your message as soon as Coffer receives it;
2. for a longer turn, a status message showing each tool call (`⏳ Bash · list home directory`) and then the reply as it is written;
3. the final reply, formatted, with the status message removed;
4. a ✅ reaction on your message when the turn finished cleanly.

Open **Chat** in the web UI and the same conversation is there, marked `via my-telegram`.

## How replies look

Telegram replies are built from the agent's Markdown.

- **Rich messages** — where the Bot API server Coffer reaches supports them, a reply with headings, lists, tables or code is sent as a rich message that keeps that structure.
- **HTML fallback** — otherwise the reply is converted to Telegram's HTML subset and split into messages of at most 4,000 characters on paragraph boundaries. A chunk Telegram refuses as HTML is re-sent as plain text.
- **Live progress** — in a direct chat, where the server supports message drafts, the reply streams into a draft that also shows Telegram's own stop button; pressing it is the same as `/stop`. Elsewhere, a status message appears once a turn has run for more than about 1.5 seconds, is edited as the turn progresses, and is deleted when the final reply is sent. A quick reply opens no status message at all.
- **Private command answers** — in a group, where the server supports ephemeral messages, the answers to `/agent`, `/model`, `/effort`, `/status` and `/help` are shown only to you.
- **Selection cards** — `/agent`, `/model` and `/effort` with no argument answer with an inline keyboard. The card's title is a heading or a bold first line.

Coffer probes each newer Bot API surface (rich messages, drafts, ephemeral messages) once. If the server refuses it as unsupported, Coffer stops trying it for the life of the daemon and uses the older mechanism, so an older server costs formatting and liveness, never delivery.

## Media

Every type Telegram attaches to a message drives a turn: photos, documents, voice messages, audio, video, animations, stickers and round video notes.

- A photo arrives at its largest size. A caption becomes the message text.
- An album — several photos sent together — is collected for one second and handled as **one** turn with all its images and the album's caption.
- Documents such as PDFs are extracted to text for the agent. Voice and audio are transcribed when speech to text is on (**Settings → Coffer's model**); otherwise the agent gets the audio file.
- A file over 20 MB — the Bot API's download limit for bots — is never fetched. The turn text notes it once, so the agent's reply mentions that it did not receive the file.
- A download that fails is noted as `[attachment '<name>' could not be downloaded]` and the turn runs on the rest of the message.

The agent sends a file back with a `MEDIA:/absolute/path` line; images arrive as photos and other files as documents, up to 50 MB. See [Channels → Sending files back](/guides/channels#sending-files-back).

::: info The token never reaches the logs
A Telegram file URL contains the bot token, so download failures are logged by error class or HTTP status only, never by URL.
:::

## Groups and forum topics

1. Add the bot to the group.
2. @mention it (`@my_coffer_bot summarise the last deploy`) or reply to one of its messages.
3. The bot answers as a reply to your message. In a forum-enabled supergroup, it answers inside the topic you wrote in.

The first addressed message from the owner registers that group as a peer of the channel. Messages from other members are refused with a short reply.

Telegram's Bot API cannot read chat history, so the bot never reads earlier messages in a group or topic: it answers the message that mentioned it. Quote the message you mean, or include the context in your own message.

The Bot API only reports mentions in the text of a plain message, so an @mention inside a photo or file caption is not recognised. Mention the bot in a separate text message.

### Privacy mode

Telegram bots start with **privacy mode on**, which means the bot only sees messages that mention it, reply to it, or are commands. That is what the default `require_mention: true` expects, so nothing needs changing.

If you set `require_mention` to `false` so the bot acts on every owner message in a group, the bot also needs to see them:

1. In BotFather, send `/setprivacy`, choose the bot and select **Disable**.
2. Remove the bot from the group and add it again. The change applies only to groups the bot joins afterwards.

Until you do, `coffer channel status` prints a `warning:` line naming this fix.

## Rotate the token

On the channel's page, choose **Edit**, enter the new token in **New bot token** and **Save changes**. The token is written under the reference the channel already uses, so pairing and machine binding are untouched. From the CLI:

```sh
coffer resource show channel my-telegram      # find the bot_token_ref
coffer credentials set channel/tg/bot-token   # paste the new token
```

## Limits

| Limit | Value |
| --- | --- |
| Reply message length | 4,000 characters per message, split on paragraphs |
| Inbound file size | 20 MB (Bot API download limit) |
| Outbound file size | 50 MB |
| Album collection window | 1 second |
| Buttons per card | 6, including paging; callback data at most 64 bytes |
| Waiting messages per conversation | 10 |

## Troubleshooting

**The bot does not answer at all.**
Run `coffer channel status my-telegram`.

- `running: False` — the channel is disabled, dormant (its scope names no agent), has no usable default agent, or is bound to another machine. The status and the channel's page say which.
- `peer: not paired` — pair first. An unpaired bot answers nobody.
- `runs on: … (another machine)` — only that machine polls the bot. Rebind with `coffer channel bind my-telegram`.

**The bot answers someone else, or stops answering after a second machine was set up.**
Two consumers are polling the same bot. This happens when the same token is registered twice, under two channel names or on two vaults. Keep one registration.

**The bot ignores messages in a group.**
Mention it or reply to it. If you turned `require_mention` off, check the privacy-mode warning above.

**`telegram.poll.retry` repeats in the daemon log.**
Polling keeps failing. Besides network trouble, Telegram refuses `getUpdates` while another program polls the same bot, and while the bot has a webhook set — for example from a bot framework you tested with earlier. Coffer does not remove a webhook for you: stop the other program, or clear the webhook with the Bot API's `deleteWebhook` method. Coffer backs off and resumes on its own. **Activity → Daemon** shows these records.

**Formatting looks flat.**
The Bot API server does not offer rich messages, so replies use the HTML fallback. Everything is still delivered.

## Related

- [Channels](/guides/channels) — commands, scope, machine binding and security for every channel.
- [SeaTalk](/guides/channels-seatalk)
- [Credentials](/guides/credentials)
- [Spec: channels/telegram](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/telegram/spec.md)
